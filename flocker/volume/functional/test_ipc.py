# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""Functional tests for IPC."""

from ..testtools import create_realistic_servicepair
from ..test.test_ipc import make_iremote_volume_manager


class RemoteVolumeManagerInterfaceTests(
        make_iremote_volume_manager(create_realistic_servicepair)):
    """
    Tests for ``RemoteVolumeManger`` as a ``IRemoteVolumeManager``.
    """
