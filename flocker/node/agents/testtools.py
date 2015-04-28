# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents``.
"""
from functools import partial
import os
import yaml

from zope.interface.verify import verifyObject
from zope.interface import implementer

from twisted.trial.unittest import SynchronousTestCase, SkipTest
from twisted.python.components import proxyForInterface

from cinderclient.client import Client as CinderClient
from novaclient.client import Client as NovaClient

from .cinder import (
    ICinderVolumeManager, INovaVolumeManager, SESSION_FACTORIES
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


@implementer(INovaVolumeManager)
class TidyNovaVolumeManager(
        proxyForInterface(INovaVolumeManager, 'original')
):
    def __init__(self, original):
        """
        :param INovaVolumeManager original: An instance of
            ``novaclient.v2.volumes.VolumeManager``.
        """
        self.original = original
        self._attached_volumes = []

    def create_server_volume(self, server_id, volume_id, device):
        """
        Wrap ``original.create_server_volume`` so as to record the
        volumes that have been attached by this API so that they can
        be later detached.
        """
        nova_attached_volume = self.original.create_server_volume(
            server_id=server_id, 
            volume_id=volume_id, 
            device=device,
        )
        self._attached_volumes.append((server_id, nova_attached_volume))
        return nova_attached_volume
        
    def _cleanup(self):
        """
        Detach any volumes that were attached by this API instance.
        """
        for server_id, volume in self._attached_volumes:
            self.original.delete_server_volume(
                server_id=server_id,
                attachment_id=volume.id
            )


class INovaVolumeManagerTestsMixin(object):
    """
    Tests for ``INovaVolumeManager`` implementations.
    """
    def test_interface(self):
        """
        ``client`` provides ``INovaVolumeManager``.
        """
        self.assertTrue(verifyObject(INovaVolumeManager, self.client))


def make_inovavolumemanager_tests(client_factory):
    """
    Build a ``TestCase`` for verifying that an implementation of
    ``INovaVolumeManager`` adheres to that interface.
    """
    class Tests(INovaVolumeManagerTestsMixin, SynchronousTestCase):
        def setUp(self):
            self.client = client_factory(test_case=self)

    return Tests


def client_from_environment(client_factory):
    """
    Create an openstack API client using credentials from a config
    file path which may be supplied as an environment variable.
    Default to ``~/acceptance.yml`` in the current user home directory, since
    that's where buildbot puts its acceptance test credentials file.

    :returns: An instance of ``keystoneclient.session.Session`` authenticated
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
    region_slug = provider_config.pop('region')
    session_factory = SESSION_FACTORIES[provider_name]
    session = session_factory(**provider_config)
    return partial(client_factory, session=session, region_name=region_slug)


def tidy_cinder_client_for_test(test_case):
    """
    Return a ``cinderclient.v1.client.Client`` whose ``volumes`` API is a
    wrapped by a ``TidyCinderVolumeManager`` and register a ``test_case``
    cleanup callback to remove any volumes that are created during each test.
    """
    client_factory = client_from_environment(client_factory=CinderClient)
    client = client_factory(version=1)
    client.volumes = TidyCinderVolumeManager(client.volumes)
    test_case.addCleanup(client.volumes._cleanup)
    return client


def tidy_nova_client_for_test(test_case):
    """
    Return a ``novaclient.v2.client.Client`` whose ``volumes`` API is a
    wrapped by a ``TidyNovaVolumeManager`` and register a ``test_case``
    cleanup callback to detach any volumes that are attached during each test.
    """
    client_factory = client_from_environment(client_factory=NovaClient)
    client = client_factory(version=2)
    client.volumes = TidyNovaVolumeManager(client.volumes)
    test_case.addCleanup(client.volumes._cleanup)
    return client
