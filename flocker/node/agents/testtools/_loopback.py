# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents.blockdevice.LoopbackBlockDeviceAPI``.
"""
from os import getuid

from pyrsistent import pmap
from twisted.python.components import proxyForInterface
from zope.interface import implementer

from ....testtools import random_name

from ..blockdevice import IBlockDeviceAPI, IProfiledBlockDeviceAPI
from ..loopback import LoopbackBlockDeviceAPI

from . import detach_destroy_volumes


def loopbackblockdeviceapi_for_test(test_case, allocation_unit=None):
    """
    :returns: A ``LoopbackBlockDeviceAPI`` with a temporary root directory
        created for the supplied ``test_case``.
    """
    user_id = getuid()
    if user_id != 0:
        test_case.skipTest(
            "``LoopbackBlockDeviceAPI`` uses ``losetup``, "
            "which requires root privileges. "
            "Required UID: 0, Found UID: {!r}".format(user_id)
        )

    root_path = test_case.mktemp()
    loopback_blockdevice_api = LoopbackBlockDeviceAPI.from_path(
        root_path=root_path,
        compute_instance_id=random_name(test_case),
        allocation_unit=allocation_unit,
    )
    test_case.addCleanup(detach_destroy_volumes, loopback_blockdevice_api)
    return loopback_blockdevice_api


@implementer(IProfiledBlockDeviceAPI)
class FakeProfiledLoopbackBlockDeviceAPI(
        proxyForInterface(IBlockDeviceAPI, "_loopback_blockdevice_api")):
    """
    Fake implementation of ``IProfiledBlockDeviceAPI`` and ``IBlockDeviceAPI``
    on top of ``LoopbackBlockDeviceAPI``. Profiles are not actually
    implemented for loopback devices, but this fake is useful for testing the
    intermediate layers.

    :ivar _loopback_blockdevice_api: The underlying ``LoopbackBlockDeviceAPI``.
    :ivar pmap dataset_profiles: A pmap from blockdevice_id to desired profile
        at creation time.
    """
    def __init__(self, loopback_blockdevice_api):
        self._loopback_blockdevice_api = loopback_blockdevice_api
        self.dataset_profiles = pmap({})

    def create_volume_with_profile(self, dataset_id, size, profile_name):
        """
        Calls the underlying ``create_volume`` on
        ``_loopback_blockdevice_api``, but records the desired profile_name for
        the purpose of test validation.
        """
        volume = self._loopback_blockdevice_api.create_volume(
            dataset_id=dataset_id, size=size)
        self.dataset_profiles = self.dataset_profiles.set(
            volume.blockdevice_id, profile_name)
        return volume


def fakeprofiledloopbackblockdeviceapi_for_test(test_case,
                                                allocation_unit=None):
    """
    Constructs a ``FakeProfiledLoopbackBlockDeviceAPI`` for use in tests that
    want to verify functionality with an ``IProfiledBlockDeviceAPI`` provider.
    """
    return FakeProfiledLoopbackBlockDeviceAPI(
        loopback_blockdevice_api=loopbackblockdeviceapi_for_test(
            test_case, allocation_unit=allocation_unit))
