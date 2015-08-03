# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node._deploy``.
"""

from uuid import uuid4

from pyrsistent import pmap, pvector, pset

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from .. import P2PManifestationDeployer, ApplicationNodeDeployer, sequentially
from ...control._model import (
    Deployment, Application, DockerImage, Node, AttachedVolume, Link,
    Manifestation, Dataset, DeploymentState, NodeState)
from .._docker import DockerClient
from ..testtools import wait_for_unit_state, if_docker_configured
from ...testtools import (
    random_name, DockerImageBuilder, assertContainsAll, loop_until)
from ...volume.testtools import create_volume_service
from ...route import make_memory_network


class P2PNodeDeployer(object):
    """
    Combination of ZFS and container deployer.

    Should really be gotten rid of:
    https://clusterhq.atlassian.net/browse/FLOC-1732
    """
    def __init__(self, hostname, volume_service, docker_client=None,
                 network=None, node_uuid=None):
        self.manifestations_deployer = P2PManifestationDeployer(
            hostname, volume_service, node_uuid=node_uuid)
        self.applications_deployer = ApplicationNodeDeployer(
            hostname, docker_client, network, node_uuid=node_uuid)
        self.hostname = hostname
        self.node_uuid = node_uuid
        self.volume_service = self.manifestations_deployer.volume_service
        self.docker_client = self.applications_deployer.docker_client
        self.network = self.applications_deployer.network

    def discover_state(self, local_state):
        d = self.manifestations_deployer.discover_state(local_state)

        def got_manifestations_state(manifestations_state):
            manifestations_state = manifestations_state[0]
            app_discovery = self.applications_deployer.discover_state(
                manifestations_state)
            app_discovery.addCallback(
                lambda app_state: [app_state[0].evolver().set(
                    "manifestations", manifestations_state.manifestations).set(
                        "paths", manifestations_state.paths).set(
                            "devices", manifestations_state.devices
                        ).persistent()])
            return app_discovery
        d.addCallback(got_manifestations_state)
        return d

    def calculate_changes(
            self, configuration, cluster_state):
        """
        Combine changes from the application and ZFS agents.
        """
        return sequentially(changes=[
            self.applications_deployer.calculate_changes(
                configuration, cluster_state),
            self.manifestations_deployer.calculate_changes(
                configuration, cluster_state),
        ])


def change_node_state(deployer, desired_configuration):
    """
    Change the local state to match the given desired state.

    :param IDeployer deployer: Deployer to discover local state and
        calculate changes.
    :param Deployment desired_configuration: The intended configuration of all
        nodes.
    :return: ``Deferred`` that fires when the necessary changes are done.
    """
    def converge():
        d = deployer.discover_state(
            NodeState(hostname=deployer.hostname, uuid=deployer.node_uuid,
                      applications=[], used_ports=[],
                      manifestations={}, paths={}, devices={}))

        def got_changes(changes):
            cluster_state = DeploymentState()
            for change in changes:
                cluster_state = change.update_cluster_state(cluster_state)
            return deployer.calculate_changes(
                desired_configuration, cluster_state)
        d.addCallback(got_changes)
        d.addCallback(lambda change: change.run(deployer))
        return d
    # Repeat a few times until things settle down:
    result = converge()
    result.addCallback(lambda _: converge())
    result.addCallback(lambda _: converge())
    return result


class DeployerTests(TestCase):
    """
    Functional tests for ``Deployer``.
    """
    @if_docker_configured
    def test_environment(self):
        """
        The environment specified in an ``Application`` is passed to the
        container.
        """
        expected_variables = frozenset({
            'key1': 'value1',
            'key2': 'value2',
        }.items())

        docker_dir = FilePath(__file__).sibling('env-docker')
        volume_service = create_volume_service(self)

        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        d = image.build()

        def image_built(image_name):
            application_name = random_name(self)

            docker_client = DockerClient()
            self.addCleanup(docker_client.remove, application_name)

            deployer = P2PNodeDeployer(
                u"localhost", volume_service, docker_client,
                make_memory_network(), node_uuid=uuid4())

            dataset = Dataset(
                dataset_id=unicode(uuid4()),
                metadata=pmap({"name": application_name}))
            manifestation = Manifestation(dataset=dataset, primary=True)
            desired_state = Deployment(nodes=frozenset([
                Node(uuid=deployer.node_uuid,
                     applications=frozenset([Application(
                         name=application_name,
                         image=DockerImage.from_string(
                             image_name),
                         environment=expected_variables,
                         volume=AttachedVolume(
                             manifestation=manifestation,
                             mountpoint=FilePath('/data'),
                         ),
                         links=frozenset(),
                     )]),
                     manifestations={
                         manifestation.dataset_id: manifestation})]))
            return change_node_state(deployer, desired_state)

        d.addCallback(image_built)
        d.addCallback(lambda _: volume_service.enumerate())
        d.addCallback(
            lambda volumes:
            list(volumes)[0].get_filesystem().get_path().child(b'env'))

        def got_result_path(result_path):
            d = loop_until(result_path.exists)
            d.addCallback(lambda _: result_path)
            return d
        d.addCallback(got_result_path)

        def started(result_path):
            contents = result_path.getContent()

            assertContainsAll(
                haystack=contents,
                test_case=self,
                needles=['{}={}\n'.format(k, v)
                         for k, v in expected_variables])
        d.addCallback(started)
        return d

    @if_docker_configured
    def test_links(self):
        """
        The links specified in an ``Application`` are passed to the
        container as environment variables.
        """
        expected_variables = frozenset({
            'ALIAS_PORT_80_TCP': 'tcp://localhost:8080',
            'ALIAS_PORT_80_TCP_PROTO': 'tcp',
            'ALIAS_PORT_80_TCP_ADDR': 'localhost',
            'ALIAS_PORT_80_TCP_PORT': '8080',
        }.items())

        volume_service = create_volume_service(self)

        docker_dir = FilePath(__file__).sibling('env-docker')
        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        d = image.build()

        def image_built(image_name):
            application_name = random_name(self)

            docker_client = DockerClient()
            self.addCleanup(docker_client.remove, application_name)

            deployer = P2PNodeDeployer(
                u"localhost", volume_service, docker_client,
                make_memory_network(), node_uuid=uuid4())

            link = Link(alias=u"alias",
                        local_port=80,
                        remote_port=8080)

            dataset = Dataset(
                dataset_id=unicode(uuid4()),
                metadata=pmap({"name": application_name}))
            manifestation = Manifestation(dataset=dataset, primary=True)
            desired_state = Deployment(nodes=frozenset([
                Node(uuid=deployer.node_uuid,
                     applications=frozenset([Application(
                         name=application_name,
                         image=DockerImage.from_string(
                             image_name),
                         links=frozenset([link]),
                         volume=AttachedVolume(
                             manifestation=manifestation,
                             mountpoint=FilePath('/data'),
                         ),
                     )]),
                     manifestations={
                         manifestation.dataset_id: manifestation})]))

            return change_node_state(deployer, desired_state)

        d.addCallback(image_built)
        d.addCallback(lambda _: volume_service.enumerate())
        d.addCallback(lambda volumes:
                      list(volumes)[0].get_filesystem().get_path().child(
                          b'env'))

        def got_result_path(result_path):
            d = loop_until(result_path.exists)
            d.addCallback(lambda _: result_path)
            return d
        d.addCallback(got_result_path)

        def started(result_path):
            contents = result_path.getContent()

            assertContainsAll(
                haystack=contents,
                test_case=self,
                needles=['{}={}\n'.format(k, v)
                         for k, v in expected_variables])
        d.addCallback(started)
        return d

    def _start_container_for_introspection(self, **kwargs):
        """
        Configure and deploy a busybox container with the given options.

        :param **kwargs: Additional arguments to pass to
            ``Application.__init__``.

        :return: ``Deferred`` that fires after convergence loop has been
            run with results of state discovery.
        """
        application_name = random_name(self)
        docker_client = DockerClient()
        self.addCleanup(docker_client.remove, application_name)

        deployer = ApplicationNodeDeployer(
            u"localhost", docker_client,
            make_memory_network(), node_uuid=uuid4())

        application = Application(
            name=application_name,
            image=DockerImage.from_string(u"busybox"),
            **kwargs)
        desired_configuration = Deployment(nodes=[
            Node(uuid=deployer.node_uuid,
                 applications=[application])])
        d = change_node_state(deployer, desired_configuration)
        d.addCallback(lambda _: deployer.discover_state(
            NodeState(hostname=deployer.hostname, uuid=deployer.node_uuid,
                      applications=[], used_ports=[],
                      manifestations={}, paths={}, devices={})))
        return d

    @if_docker_configured
    def test_links_lowercase(self):
        """
        Lower-cased link aliases do not result in lack of covergence.

        Environment variables introspected by the Docker client for links
        are all upper-case, a source of potential problems in detecting
        the state.
        """
        link = Link(alias=u"alias",
                    local_port=80,
                    remote_port=8080)
        d = self._start_container_for_introspection(
            links=[link],
            command_line=[u"nc", u"-l", u"-p", u"8080"])
        d.addCallback(
            lambda results: self.assertIn(
                pset([link]),
                [app.links for app in results[0].applications]))
        return d

    @if_docker_configured
    def test_command_line_introspection(self):
        """
        Checking the command-line status results in same command-line we
        passed in.
        """
        command_line = pvector([u"nc", u"-l", u"-p", u"8080"])
        d = self._start_container_for_introspection(command_line=command_line)
        d.addCallback(
            lambda results: self.assertIn(
                command_line,
                [app.command_line for app in results[0].applications]))
        return d

    @if_docker_configured
    def test_memory_limit(self):
        """
        The memory limit number specified in an ``Application`` is passed to
        the container.
        """
        EXPECTED_MEMORY_LIMIT = 100000000
        image = DockerImage.from_string(u"openshift/busybox-http-app")

        application_name = random_name(self)

        docker_client = DockerClient()
        self.addCleanup(docker_client.remove, application_name)

        deployer = ApplicationNodeDeployer(
            u"localhost", docker_client, make_memory_network(),
            node_uuid=uuid4())

        desired_state = Deployment(nodes=frozenset([
            Node(uuid=deployer.node_uuid,
                 applications=frozenset([Application(
                     name=application_name,
                     image=image,
                     memory_limit=EXPECTED_MEMORY_LIMIT
                     )]))]))

        d = change_node_state(deployer, desired_state)
        d.addCallback(lambda _: wait_for_unit_state(
            docker_client,
            application_name,
            [u'active'])
        )

        def inspect_application(_):
            deferred_list = docker_client.list()

            def app_memory(units):
                unit = units.pop()
                self.assertEqual(unit.mem_limit, EXPECTED_MEMORY_LIMIT)
                return deferred_list

            deferred_list.addCallback(app_memory)
        d.addCallback(inspect_application)
        return d

    @if_docker_configured
    def test_cpu_shares(self):
        """
        The CPU shares number specified in an ``Application`` is passed to the
        container.
        """
        EXPECTED_CPU_SHARES = 512

        image = DockerImage.from_string(u"openshift/busybox-http-app")

        application_name = random_name(self)

        docker_client = DockerClient()
        self.addCleanup(docker_client.remove, application_name)

        deployer = ApplicationNodeDeployer(
            u"localhost", docker_client, make_memory_network(),
            node_uuid=uuid4())

        desired_state = Deployment(nodes=frozenset([
            Node(uuid=deployer.node_uuid,
                 applications=frozenset([Application(
                     name=application_name,
                     image=image,
                     cpu_shares=EXPECTED_CPU_SHARES
                     )]))]))

        d = change_node_state(deployer, desired_state)
        d.addCallback(lambda _: wait_for_unit_state(
            docker_client,
            application_name,
            [u'active'])
        )

        def inspect_application(_):
            deferred_list = docker_client.list()

            def app_memory(units):
                unit = units.pop()
                self.assertEqual(unit.cpu_shares, EXPECTED_CPU_SHARES)
                return deferred_list

            deferred_list.addCallback(app_memory)
        d.addCallback(inspect_application)
        return d
