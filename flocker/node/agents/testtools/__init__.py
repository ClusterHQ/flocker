# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents``.
"""

from ._cinder import (
    make_icindervolumemanager_tests,
    make_inovavolumemanager_tests,
)
from ._blockdevice import (
    FakeCloudAPI,
    dataset_agent_api_for_test,
    detach_destroy_volumes,
    make_iblockdeviceapi_tests,
    make_icloudapi_tests,
    make_iprofiledblockdeviceapi_tests,
    mountroot_for_test,
    umount,
    umount_all,
)
from ._loopback import (
    fakeprofiledloopbackblockdeviceapi_for_test,
    loopbackblockdeviceapi_for_test,
)
__all__ = [
    'FakeCloudAPI',
    'dataset_agent_api_for_test',
    'detach_destroy_volumes',
    'fakeprofiledloopbackblockdeviceapi_for_test',
    'loopbackblockdeviceapi_for_test',
    'make_iblockdeviceapi_tests',
    'make_icindervolumemanager_tests',
    'make_icloudapi_tests',
    'make_inovavolumemanager_tests',
    'make_iprofiledblockdeviceapi_tests',
    'mountroot_for_test',
    'umount',
    'umount_all',
]
