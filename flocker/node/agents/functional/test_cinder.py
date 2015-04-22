# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.cinder`` using a real OpenStack
cluster.
"""

# A helper to check the environment for username and API key
# Create an authenticated cinder API instance
# Supply that to make_iblockdeviceapi_tests

from uuid import uuid4

from ..cinder import cinder_api
from ..testtools import (
    make_iblockdeviceapi_tests, todo_except, tidy_cinder_client_for_test
)


def cinderblockdeviceapi_for_test(test_case):
    """
    """
    return cinder_api(
        cinder_client=tidy_cinder_client_for_test(test_case),
        cluster_id=unicode(uuid4()),
    )


@todo_except(
    supported_tests=[
        'test_interface',
        'test_created_is_listed',
        'test_created_volume_attributes',
        'test_list_volume_empty',
        'test_listed_volume_attributes',
    ]
)
class CinderBlockDeviceAPITests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=cinderblockdeviceapi_for_test
        )
):
    """
    Interface adherence Tests for ``CinderBlockDeviceAPI``.
    """
