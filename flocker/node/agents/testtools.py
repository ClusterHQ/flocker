# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents``.
"""

from zope.interface.verify import verifyObject
from zope.interface import implementer, Interface

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.components import proxyForInterface

from ...testtools import require_environment_variables
from .cinder import authenticated_cinder_client
# make_iblockdeviceapi_tests should really be here, but I want to keep the
# branch size down
from .test.test_blockdevice import make_iblockdeviceapi_tests


GIBIBYTE = 2 ** 30
REALISTIC_BLOCKDEVICE_SIZE = 4 * GIBIBYTE
LOOPBACK_BLOCKDEVICE_SIZE = 1024 * 1024 * 64


def require_cinder_credentials(original):
    """
    Raise ``SkipTest`` unless the cinder username and api key are present in
    the environment.
    """
    decorator = require_environment_variables(
        required_keys=['OPENSTACK_API_USER', 'OPENSTACK_API_KEY']
    )
    return decorator(original)


class ICinderVolumeManager(Interface):
    """
    The parts of the ``cinder.client.Client.volumes`` that we use.
    """
    def create(size, metadata=None):
        """
        Create a new cinder volume and return a representation of that volume.
        """

    def list():
        """
        Return a list of all the cinder volumes known to this client; limited
        by the access granted for a particular API key and the region.
        """

    def set_metadata(volume, metadata):
        """
        Set the metadata for a cinder volume.
        """


@implementer(ICinderVolumeManager)
class TidyCinderVolumeManager(
        proxyForInterface(ICinderVolumeManager, 'original')
):
    def __init__(self, original):
        self.original = original
        self._created_volumes = []

    def create(self, size, metadata=None):
        """
        Call the original VolumeManager and record the volume so that it can be
        cleaned up later.
        """
        volume = self.original.create(size=size, metadata=metadata)
        self._created_volumes.append(volume)
        return volume

    def _cleanup(self):
        """
        Remove all the volumes that have been created by this VolumeManager
        wrapper.
        """
        for volume in self._created_volumes:
            self.original.delete(volume)


class ICinderVolumeManagerTestsMixin(object):
    """
    Tests for ``ICinderVolumeManager`` implementations.
    """
    def test_interface(self):
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


@require_cinder_credentials
def cinder_client_from_environment(OPENSTACK_API_USER, OPENSTACK_API_KEY):
    """
    Create a ``cinder.client.Client`` using credentials from the process
    environment which are supplied to the RackspaceAuth plugin.
    """
    return authenticated_cinder_client(
        username=OPENSTACK_API_USER,
        api_key=OPENSTACK_API_KEY,
        region='DFW',
    )


def tidy_cinder_client_for_test(test_case):
    """
    Return a ``cinder.client.Client`` whose ``volumes`` API is a wrapped by a
    ``TidyCinderVolumeManager`` and register a ``test_case`` cleanup callback
    to remove any volumes that are created during the course of a test.
    """
    client = cinder_client_from_environment()
    client.volumes = TidyCinderVolumeManager(client.volumes)
    test_case.addCleanup(client.volumes._cleanup)
    return client
