# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._deploy``.
"""

from twisted.trial.unittest import SynchronousTestCase

from .._deploy import Deployment
from .._model import Application, DockerImage
from ..gear import GearClient, FakeGearClient, AlreadyExists


class DeploymentAttributesTests(SynchronousTestCase):
    """
    Tests for attributes and initialiser arguments of `Deployment`.
    """
    def test_gear_client_default(self):
        """
        ``Deployment._gear_client`` is a ``GearClient`` by default.
        """
        self.assertIsInstance(
            Deployment()._gear_client,
            GearClient
        )

    def test_gear_override(self):
        """
        ``Deployment._gear_client`` can be overridden in the constructor.
        """
        dummy_gear_client = object()
        self.assertIs(
            dummy_gear_client,
            Deployment(gear_client=dummy_gear_client)._gear_client
        )


class DeploymentStartContainerTests(SynchronousTestCase):
    """
    Tests for `Deployment.start_container`.
    """
    def test_start(self):
        """
        `Deployment.start_container` accepts an application object and returns a
        deferred which fires when the `gear` unit has been added and started.
        """
        fake_gear = FakeGearClient()
        api = Deployment(gear_client=fake_gear)
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )
        start_result = api.start_container(application=application)
        exists_result = fake_gear.exists(unit_name=application.name)

        self.assertEqual(
            (None, True),
            (self.successResultOf(start_result),
             self.successResultOf(exists_result))
        )

    def test_already_exists(self):
        """
        ``Deployment.start_container`` returns a deferred which errbacks with an
        ``AlreadyExists`` error if there is already a unit with the supplied
        application name.
        """
        api = Deployment(gear_client=FakeGearClient())
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )
        result1 = api.start_container(application=application)
        self.successResultOf(result1)

        result2 = api.start_container(application=application)
        self.failureResultOf(result2, AlreadyExists)


class DeploymentStopContainerTests(SynchronousTestCase):
    """
    Tests for ``Deployment.stop_container``.
    """
    def test_stop(self):
        """
        ``Deployment.stop_container`` accepts an application object and returns
        a deferred which fires when the `gear` unit has been removed.
        """
        fake_gear = FakeGearClient()
        api = Deployment(gear_client=fake_gear)
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker', tag=u'release-14.0')
        )

        api.start_container(application=application)
        existed = fake_gear.exists(application.name)

        stop_result = api.stop_container(application=application)
        exists_result = fake_gear.exists(unit_name=application.name)

        self.assertEqual(
            (None, True, False),
            (self.successResultOf(stop_result),
             self.successResultOf(existed),
             self.successResultOf(exists_result))
        )


    def test_does_not_exist(self):
        """
        ``Deployment.stop_container`` does not errback if the application does
        not exist.
        """
        api = Deployment(gear_client=FakeGearClient())
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker', tag=u'release-14.0')
        )

        result = api.stop_container(application=application)
        result = self.successResultOf(result)
        self.assertIs(None, result)
