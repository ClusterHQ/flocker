# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node._deploy``.
"""

from subprocess import check_call

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from .. import (
    Deployer, Deployment, Application, DockerImage, Node, AttachedVolume)
from ..gear import GearClient
from ..testtools import wait_for_unit_state, if_gear_configured
from ...testtools import random_name, DockerImageBuilder, assertContainsAll
from ...volume.testtools import create_volume_service
from ...route import make_memory_network


class DeployerTests(TestCase):
    """
    Functional tests for ``Deployer``.
    """
    @if_gear_configured
    def test_restart(self):
        """
        Stopped applications that are supposed to be running are restarted
        when ``Deployer.change_node_state`` is run.
        """
        name = random_name()
        gear_client = GearClient("127.0.0.1")
        deployer = Deployer(create_volume_service(self), gear_client,
                            make_memory_network())
        self.addCleanup(gear_client.remove, name)

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
        d.addCallback(lambda _: wait_for_unit_state(gear_client, name,
                                                    [u'active']))

        def started(_):
            # Now that it's running, stop it behind our back:
            check_call([b"gear", b"stop", name])
            return wait_for_unit_state(gear_client, name,
                                       [u'inactive', u'failed'])
        d.addCallback(started)

        def stopped(_):
            # Redeploy, which should restart it:
            return deployer.change_node_state(desired_state, desired_state,
                                              u"localhost")
        d.addCallback(stopped)
        d.addCallback(lambda _: wait_for_unit_state(gear_client, name,
                                                    [u'active']))

        # Test will timeout if unit was not restarted:
        return d

    @if_gear_configured
    def test_environment(self):
        docker_dir = FilePath(self.mktemp())
        docker_dir.makedirs()
        docker_dir.child(b"Dockerfile").setContent(
            b'FROM busybox\n'
            b'CMD ["/bin/sh",  "-c", "env > /data/env && sleep 1"]'
        )
        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        image_name = image.build()

        application_name = random_name()

        gear_client = GearClient("127.0.0.1")
        self.addCleanup(gear_client.remove, application_name)

        volume_service = create_volume_service(self)
        deployer = Deployer(volume_service, gear_client,
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

        d = deployer.change_node_state(desired_state,
                                       Deployment(nodes=frozenset()),
                                       u"localhost")
        d.addCallback(lambda _: wait_for_unit_state(gear_client,
                                                    application_name,
                                                    [u'active']))

        def started(_):
            volume = volume_service.get(application_name)
            path = volume.get_filesystem().get_path()
            contents = path.child(b'env').getContent()

            assertContainsAll(
                haystack=contents,
                test_case=self,
                needles=['{}={}\n'.format(k, v)
                         for k, v in expected_variables])
        d.addCallback(started)
        return d
