# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.loopback``.
"""
from functools import partial
from os import getuid
from uuid import uuid4

from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests,
    LOOPBACK_ALLOCATION_UNIT, LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
    detach_destroy_volumes,
)
from ....ca.testtools import get_credential_sets
from ....testtools import MemoryCoreReactor
from ...script import AgentService


def loopbackblockdeviceapi_for_test(test_case, allocation_unit=None):
    """
    Do some setup common to all of the ``AgentService`` test cases.

    :param test: A ``TestCase`` instance.
    """
    user_id = getuid()
    if user_id != 0:
        test_case.skipTest(
            "``LoopbackBlockDeviceAPI`` uses ``losetup``, "
            "which requires root privileges. "
            "Required UID: 0, Found UID: {!r}".format(user_id)
        )

    ca_set = get_credential_sets()[0]
    host = b"192.0.2.5"
    port = 54123
    reactor = MemoryCoreReactor()

    agent_service = AgentService(
        reactor=reactor,
        control_service_host=host,
        control_service_port=port,
        node_credential=ca_set.node,
        ca_certificate=ca_set.root.credential.certificate,
        backend_name=u"anything",
        api_args={},
    )
    agent_service = agent_service.set(
        "backend_name", u"loopback"
    ).set(
        "api_args", {
            "root_path": test_case.make_temporary_directory().path,
            "allocation_unit": allocation_unit
        }
    )
    api = agent_service.get_api()
    test_case.addCleanup(detach_destroy_volumes, api)
    return api


class LoopbackBlockDeviceAPITests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=partial(
                loopbackblockdeviceapi_for_test,
                allocation_unit=LOOPBACK_ALLOCATION_UNIT
            ),
            minimum_allocatable_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            device_allocation_unit=None,
            unknown_blockdevice_id_factory=lambda test: unicode(uuid4()),
        )
):
    """
    Interface adherence Tests for ``LoopbackBlockDeviceAPI``.
    """
