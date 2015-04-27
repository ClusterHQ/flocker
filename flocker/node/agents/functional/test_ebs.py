# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.ebs`` using an EC2 cluster.

"""

from uuid import uuid4

from ..ebs import EBSBlockDeviceAPI
from ..testtools import ebs_client_from_environment
from ..test.test_blockdevice import make_iblockdeviceapi_tests


def ebsblockdeviceapi_for_test(test_case, cluster_id):
    return EBSBlockDeviceAPI(
        ebs_client=ebs_client_from_environment(),
        cluster_id=cluster_id
    )


class EBSBlockDeviceAPIInterfaceTests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=(
                lambda test_case: ebsblockdeviceapi_for_test(
                    test_case=test_case,
                    cluster_id=uuid4()
                )
            )
        )
):

    """
    Interface adherence Tests for ``EBSBlockDeviceAPI``.
    """
