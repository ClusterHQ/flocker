# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node._deploy``.
"""

from uuid import uuid4

from pyrsistent import pmap

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from .. import P2PManifestationDeployer, ApplicationNodeDeployer, Sequentially
from ...control._model import (
    Deployment, Application, DockerImage, Node, AttachedVolume, Link,
    Manifestation, Dataset, DeploymentState, NodeState)
from .._docker import DockerClient
from ..testtools import wait_for_unit_state, if_docker_configured
from ...testtools import (
    random_name, DockerImageBuilder, assertContainsAll, loop_until,
    run_process)
from ...volume.testtools import create_volume_service
from ...route import make_memory_network


class P2PNodeDeployer(object):
    """
    Combination of ZFS and container deployer.
    """
    def __init__(self, hostname, volume_service, docker_client=None,
                 network=None):
        self.manifestations_deployer = P2PManifestationDeployer(
            hostname, volume_service)
        self.applications_deployer = ApplicationNodeDeployer(
            hostname, docker_client, network)
        self.hostname = hostname
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
                lambda app_state: [app_state[0].set(
                    "manifestations", manifestations_state.manifestations).set(
                        "paths", manifestations_state.paths)])
            return app_discovery
        d.addCallback(got_manifestations_state)
        return d

    def calculate_changes(
            self, configuration, cluster_state):
        """
        Combine changes from the application and ZFS agents.
        """
        return Sequentially(changes=[
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
        d = deployer.discover_state(NodeState(hostname=deployer.hostname))

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
    def test_restart(self):
        """
        Stopped applications that are supposed to be running are restarted
        when the calcualted actions are run.
        """
        name = random_name()
        docker_client = DockerClient()
        deployer = ApplicationNodeDeployer(
            u"localhost", docker_client, make_memory_network())
        self.addCleanup(docker_client.remove, name)

        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
                 applications=frozenset([Application(
                     name=name,
                     image=DockerImage.from_string(
                         u"openshift/busybox-http-app"),
                     links=frozenset(),
                     )]))]))

        d = change_node_state(deployer, desired_state)
        d.addCallback(lambda _: wait_for_unit_state(docker_client, name,
                                                    [u'active']))

        def started(_):
            # Now that it's running, stop it behind our back:
            run_process([b"docker", b"stop",
                         docker_client._to_container_name(name)])
            return wait_for_unit_state(docker_client, name,
                                       [u'inactive', u'failed'])
        d.addCallback(started)

        def stopped(_):
            # Redeploy, which should restart it:
            return change_node_state(deployer, desired_state)
        d.addCallback(stopped)
        d.addCallback(lambda _: wait_for_unit_state(docker_client, name,
                                                    [u'active']))

        # Test will timeout if unit was not restarted:
        return d

    @if_docker_configured
    def test_environment(self):
        """
        The environment specified in an ``Application`` is passed to the
        container.
        """
        docker_dir = FilePath(__file__).sibling('env-docker')
        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        image_name = image.build()

        application_name = random_name()

        docker_client = DockerClient()
        self.addCleanup(docker_client.remove, application_name)

        volume_service = create_volume_service(self)
        deployer = P2PNodeDeployer(
            u"localhost", volume_service, docker_client,
            make_memory_network())

        expected_variables = frozenset({
            'key1': 'value1',
            'key2': 'value2',
        }.items())

        dataset = Dataset(
            dataset_id=unicode(uuid4()),
            metadata=pmap({"name": application_name}))
        manifestation = Manifestation(dataset=dataset, primary=True)
        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
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
                 manifestations={manifestation.dataset_id: manifestation})]))

        d = change_node_state(deployer, desired_state)
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

    @if_docker_configured
    def test_links(self):
        """
        The links specified in an ``Application`` are passed to the
        container as environment variables.
        """
        docker_dir = FilePath(__file__).sibling('env-docker')
        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        image_name = image.build()

        application_name = random_name()

        docker_client = DockerClient()
        self.addCleanup(docker_client.remove, application_name)

        volume_service = create_volume_service(self)
        deployer = P2PNodeDeployer(
            u"localhost", volume_service, docker_client,
            make_memory_network())

        expected_variables = frozenset({
            'ALIAS_PORT_80_TCP': 'tcp://localhost:8080',
            'ALIAS_PORT_80_TCP_PROTO': 'tcp',
            'ALIAS_PORT_80_TCP_ADDR': 'localhost',
            'ALIAS_PORT_80_TCP_PORT': '8080',
        }.items())

        link = Link(alias=u"alias",
                    local_port=80,
                    remote_port=8080)

        dataset = Dataset(
            dataset_id=unicode(uuid4()),
            metadata=pmap({"name": application_name}))
        manifestation = Manifestation(dataset=dataset, primary=True)
        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
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
                 manifestations={manifestation.dataset_id: manifestation})]))

        d = change_node_state(deployer, desired_state)
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

    @if_docker_configured
    def test_memory_limit(self):
        """
        The memory limit number specified in an ``Application`` is passed to
        the container.
        """
        EXPECTED_MEMORY_LIMIT = 100000000
        image = DockerImage.from_string(u"openshift/busybox-http-app")

        application_name = random_name()

        docker_client = DockerClient()
        self.addCleanup(docker_client.remove, application_name)

        deployer = ApplicationNodeDeployer(
            u"localhost", docker_client, make_memory_network())

        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
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

        application_name = random_name()

        docker_client = DockerClient()
        self.addCleanup(docker_client.remove, application_name)

        deployer = ApplicationNodeDeployer(
            u"localhost", docker_client, make_memory_network())

        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
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
