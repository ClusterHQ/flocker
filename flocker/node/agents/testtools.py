# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents``.
"""

import os
import yaml

from zope.interface.verify import verifyObject
from zope.interface import implementer

from twisted.trial.unittest import SynchronousTestCase, SkipTest
from twisted.python.components import proxyForInterface

from .cinder import (
    ICinderVolumeManager, CINDER_CLIENT_FACTORIES
)


DEFAULT_CLOUD_PROVIDER = 'rackspace'


@implementer(ICinderVolumeManager)
class TidyCinderVolumeManager(
        proxyForInterface(ICinderVolumeManager, 'original')
):
    def __init__(self, original):
        """
        :param ICinderVolumeManager original: An instance of
            ``cinderclient.v1.volumes.VolumeManager``.
        """
        self.original = original
        self._created_volumes = []

    def create(self, size, metadata=None):
        """
        Call the original ``VolumeManager.create`` and record the returned
        ``Volume`` so that it can be cleaned up later.

        See ``cinderclient.v1.volumes.VolumeManager.create`` for parameter and
        return type documentation.
        """
        volume = self.original.create(size=size, metadata=metadata)
        self._created_volumes.append(volume)
        return volume

    def attach(self, volume, instance_uuid, mountpoint):
        """
        This may not be necessary....let's see.
        """
        return self.original.attach(
            volume=volume,
            instance_uuid=instance_uuid,
            mountpoint=mountpoint,
        )

    def _cleanup(self):
        """
        Remove all the volumes that have been created by this VolumeManager
        wrapper.

        XXX: Some tests will have deleted the volume already, this method
        should probably deal with already deleted volumes.
        """
        for volume in self._created_volumes:
            self.original.delete(volume)


class ICinderVolumeManagerTestsMixin(object):
    """
    Tests for ``ICinderVolumeManager`` implementations.
    """
    def test_interface(self):
        """
        ``client`` provides ``ICinderVolumeManager``.
        """
        self.assertTrue(verifyObject(ICinderVolumeManager, self.client))


def make_icindervolumemanager_tests(client_factory):
    """
    Build a ``TestCase`` for verifying that an implementation of
    ``ICinderVolumeManager`` adheres to that interface.
    """
    class Tests(ICinderVolumeManagerTestsMixin, SynchronousTestCase):
        def setUp(self):
            self.client = client_factory(test_case=self)

    return Tests


def cinder_client_from_environment():
    """
    Create a ``cinderclient.v1.client.Client`` using credentials from a config
    file path which may be supplied as an environment variable.
    Default to ``~/acceptance.yml`` in the current user home directory, since
    that's where buildbot puts its acceptance test credentials file.

    :returns: An instance of ``cinderclient.v1.client.Client`` authenticated
        using provider specific credentials found in ``CLOUD_CONFIG_FILE``.
    :raises: ``SkipTest`` if a ``CLOUD_CONFIG_FILE`` was not set and the
        default config file could not be read.
    """
    config_file_path = os.environ.get('CLOUD_CONFIG_FILE')
    if config_file_path is not None:
        config_file = open(config_file_path)
    else:
        raise SkipTest(
            'Supply the path to a cloud credentials file '
            'using the CLOUD_CONFIG_FILE environment variable. '
            'See: '
            'https://docs.clusterhq.com/en/latest/gettinginvolved/acceptance-testing.html '  # noqa
            'for details of the expected format.'
        )

    config = yaml.load(config_file.read())
    provider_name = os.environ.get('CLOUD_PROVIDER', DEFAULT_CLOUD_PROVIDER)
    provider_config = config[provider_name]
    cinder_client_factory = CINDER_CLIENT_FACTORIES[provider_name]
    return cinder_client_factory(**provider_config)


def tidy_cinder_client_for_test(test_case):
    """
    Return a ``cinderclient.v1.client.Client`` whose ``volumes`` API is a
    wrapped by a ``TidyCinderVolumeManager`` and register a ``test_case``
    cleanup callback to remove any volumes that are created during each test.
    """
    client = cinder_client_from_environment()
    client.volumes = TidyCinderVolumeManager(client.volumes)
    test_case.addCleanup(client.volumes._cleanup)
    return client
