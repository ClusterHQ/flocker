# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node._deploy``.
"""

from subprocess import check_call

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from .. import (
    Deployer, Deployment, Application, DockerImage, Node, AttachedVolume, Link)
from .._deploy import _to_volume_name
from .._docker import DockerClient
from ..testtools import wait_for_unit_state, if_docker_configured
from ...testtools import (
    random_name, DockerImageBuilder, assertContainsAll, loop_until)
from ...volume.testtools import create_volume_service
from ...route import make_memory_network


class DeployerTests(TestCase):
    """
    Functional tests for ``Deployer``.
    """
    @if_docker_configured
    def test_restart(self):
        """
        Stopped applications that are supposed to be running are restarted
        when ``Deployer.change_node_state`` is run.
        """
        name = random_name()
        docker_client = DockerClient()
        deployer = Deployer(create_volume_service(self), docker_client,
                            make_memory_network())
        self.addCleanup(docker_client.remove, name)

        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
                 applications=frozenset([Application(
                     name=name,
                     image=DockerImage.from_string(
                         u"openshift/busybox-http-app"),
                     links=frozenset(),
                     )]))]))

        d = deployer.change_node_state(desired_state,
                                       Deployment(nodes=frozenset()),
                                       u"localhost")
        d.addCallback(lambda _: wait_for_unit_state(docker_client, name,
                                                    [u'active']))

        def started(_):
            # Now that it's running, stop it behind our back:
            check_call([b"docker", b"stop",
                        docker_client._to_container_name(name)])
            return wait_for_unit_state(docker_client, name,
                                       [u'inactive', u'failed'])
        d.addCallback(started)

        def stopped(_):
            # Redeploy, which should restart it:
            return deployer.change_node_state(desired_state, desired_state,
                                              u"localhost")
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
        deployer = Deployer(volume_service, docker_client,
                            make_memory_network())

        expected_variables = frozenset({
            'key1': 'value1',
            'key2': 'value2',
        }.items())

        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
                 applications=frozenset([Application(
                     name=application_name,
                     image=DockerImage.from_string(
                         image_name),
                     environment=expected_variables,
                     volume=AttachedVolume(
                         name=application_name,
                         mountpoint=FilePath('/data'),
                         ),
                     links=frozenset(),
                     )]))]))

        volume = volume_service.get(_to_volume_name(application_name))
        result_path = volume.get_filesystem().get_path().child(b'env')

        d = deployer.change_node_state(desired_state,
                                       Deployment(nodes=frozenset()),
                                       u"localhost")
        d.addCallback(lambda _: loop_until(result_path.exists))

        def started(_):
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
        deployer = Deployer(volume_service, docker_client,
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

        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
                 applications=frozenset([Application(
                     name=application_name,
                     image=DockerImage.from_string(
                         image_name),
                     links=frozenset([link]),
                     volume=AttachedVolume(
                         name=application_name,
                         mountpoint=FilePath('/data'),
                         ),
                     )]))]))

        volume = volume_service.get(_to_volume_name(application_name))
        result_path = volume.get_filesystem().get_path().child(b'env')

        d = deployer.change_node_state(desired_state,
                                       Deployment(nodes=frozenset()),
                                       u"localhost")
        d.addCallback(lambda _: loop_until(result_path.exists))

        def started(_):
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

        volume_service = create_volume_service(self)
        deployer = Deployer(volume_service, docker_client,
                            make_memory_network())

        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
                 applications=frozenset([Application(
                     name=application_name,
                     image=image,
                     memory_limit=EXPECTED_MEMORY_LIMIT
                     )]))]))

        d = deployer.change_node_state(desired_state,
                                       Deployment(nodes=frozenset()),
                                       u"localhost")
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

        volume_service = create_volume_service(self)
        deployer = Deployer(volume_service, docker_client,
                            make_memory_network())

        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
                 applications=frozenset([Application(
                     name=application_name,
                     image=image,
                     cpu_shares=EXPECTED_CPU_SHARES
                     )]))]))

        d = deployer.change_node_state(desired_state,
                                       Deployment(nodes=frozenset()),
                                       u"localhost")
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


    def test_restart_policy_never(self):
        """
        An ``Application`` with a restart policy of never isn't restarted
        after it exits.
        """
        # Start a container that immediately exits
        # Verify that the container isn't started.


    def test_restart_policy_always(self):
        """
        An ``Application`` with a restart policy of always is restarted
        after it exits.
        """
        # Start a container that
        # - imediately exits on the first run
        # - sleeps forever on subsequent runs
        # (this will use a volume for tracking state
        # Verify that
        # - the container has run twice (by inspecting the volume)
        # - the container is still running

    def test_restart_policy_on_failure(self):
        """
        An ``Application`` with a restart policy of on-failure is restarted
        after it exits with a non-zero result.
        """
        # Start a container that
        # - immediately exits with a failure on the first run
        # - immediately exits with a success on subsequent runs
        # Verify that
        # - the container is stopped
        # - the container ran twice

    def test_restart_policy_on_failure_maximum_count(self):
        """
        An ``Application`` with a restart policy of on-failure and a maximum
        retry count is not restarted if it fails more times than the specified
        maximum.
        """
        # Start a container that
        # - immediately exits with a failure state
        # - records the number of times it has been run
        # Verify that
        # - the container isn't runnnig
        # - the container started the appropiate number of times
