# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.cinder`` using a real OpenStack
cluster.
"""

# A helper to check the environment for username and API key
# Create an authenticated cinder API instance
# Supply that to make_iblockdeviceapi_tests

from uuid import uuid4

from ..cinder import CinderBlockDeviceAPI
from ..testtools import make_iblockdeviceapi_tests


def cinderblockdeviceapi_for_test(test_case):
    """
    """
    return CinderBlockDeviceAPI(cluster_id=unicode(uuid4()), region='DFW')


class CinderBlockDeviceAPITests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=cinderblockdeviceapi_for_test
        )
):
    """
    Interface adherence Tests for ``CinderBlockDeviceAPI``.
    """
