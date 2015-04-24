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

from .cinder import authenticated_cinder_client, ICinderVolumeManager


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
        using Rackspace credentials and against the Rackspace Keystone server.
    :raises: ``SkipTest`` if a ``CLOUD_CONFIG_PATH`` was not set and the
        default config file could not be read.
    """
    default_config_file_path = os.path.expanduser('~/acceptance.yml')
    config_file_path = os.environ.get('CLOUD_CONFIG_PATH')
    if config_file_path is not None:
        config_file = open(config_file_path)
    else:
        try:
            config_file = open(default_config_file_path)
        except IOError as e:
            raise SkipTest(
                'CLOUD_CONFIG_PATH environment variable was not set '
                'and the default config path ({}) could not be read. '
                '{}'.format(default_config_file_path, e)
            )

    config = yaml.load(config_file.read())
    rackspace_config = config['rackspace']

    return authenticated_cinder_client(
        username=rackspace_config['username'],
        api_key=rackspace_config['key'],
        # XXX: Seems that Rackspace region slugs are case sensitive...when used
        # with python-keystone anyway.
        region=rackspace_config['region'].upper(),
    )


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
