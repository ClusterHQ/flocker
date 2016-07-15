# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents``.
"""

from ._cinder import (
    make_icindervolumemanager_tests,
    make_inovavolumemanager_tests,
    mimic_for_test,
)
from ._blockdevice import (
    FakeCloudAPI,
    InvalidConfig,
    detach_destroy_volumes,
    get_blockdevice_config,
    get_blockdeviceapi_with_cleanup,
    get_ec2_client_for_test,
    get_minimum_allocatable_size,
    get_openstack_region_for_test,
    make_iblockdeviceapi_tests,
    make_icloudapi_tests,
    make_iprofiledblockdeviceapi_tests,
    mountroot_for_test,
    require_backend,
    umount,
    umount_all,
)
from ._loopback import (
    fakeprofiledloopbackblockdeviceapi_for_test,
    loopbackblockdeviceapi_for_test,
)
__all__ = [
    'FakeCloudAPI',
    'InvalidConfig',
    'detach_destroy_volumes',
    'fakeprofiledloopbackblockdeviceapi_for_test',
    'get_blockdevice_config',
    'get_blockdeviceapi_with_cleanup',
    'get_ec2_client_for_test',
    'get_minimum_allocatable_size',
    'get_openstack_region_for_test',
    'loopbackblockdeviceapi_for_test',
    'make_iblockdeviceapi_tests',
    'make_icindervolumemanager_tests',
    'make_icloudapi_tests',
    'make_inovavolumemanager_tests',
    'make_iprofiledblockdeviceapi_tests',
    'mimic_for_test',
    'mountroot_for_test',
    'require_backend',
    'umount',
    'umount_all',
]
