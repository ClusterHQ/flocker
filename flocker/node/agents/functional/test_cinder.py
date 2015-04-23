# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.cinder`` using a real OpenStack
cluster.
"""

from uuid import uuid4

from ....testtools import skip_except
from ..cinder import cinder_api
from ..testtools import tidy_cinder_client_for_test
# make_iblockdeviceapi_tests should really be in flocker.node.agents.testtools,
# but I want to keep the branch size down
from ..test.test_blockdevice import make_iblockdeviceapi_tests


def cinderblockdeviceapi_for_test(test_case):
    """
    Create a ``CinderBlockDeviceAPI`` instance for use in tests.

    :param TestCase test_case: The test being run.
    :returns: A ``CinderBlockDeviceAPI`` instance whose underlying
        ``cinderclient.v2.client.Client`` has a ``volumes`` attribute wrapped
        by ``TidyCinderVolumeManager`` to cleanup any lingering volumes that
        are created during the course of ``test_case``
    """
    return cinder_api(
        cinder_client=tidy_cinder_client_for_test(test_case),
        cluster_id=unicode(uuid4()),
    )


# ``CinderBlockDeviceAPI`` only implements the ``create`` and ``list`` parts of
# ``IBlockDeviceAPI``. Skip the rest of the tests for now.
@skip_except(
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
