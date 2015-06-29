# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.ebs``.
"""

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase

from ..ebs import AttachedUnexpectedDevice, _expected_device


class AttachedUnexpectedDeviceTests(SynchronousTestCase):
    """
    Tests for ``AttachedUnexpectedDevice``.
    """
    def test_repr(self):
        """
        The string representation of ``AttachedUnexpectedDevice`` includes the
        requested device name and the discovered device name.
        """
        requested = FilePath(b"/dev/sda")
        discovered = FilePath(b"/dev/sdb")
        expected = (
            "AttachedUnexpectedDevice("
            "requested='/dev/sda', discovered='/dev/sdb'"
            ")"
        )
        self.assertEqual(
            expected,
            repr(AttachedUnexpectedDevice(requested, discovered))
        )


class ExpectedDeviceTests(SynchronousTestCase):
    """
    Tests for ``_expected_device``.
    """
    def test_sdX_to_xvdX(self):
        """
        ``sdX``-style devices are rewritten to corresponding ``xvdX`` devices.
        """
        self.assertEqual(
            (FilePath(b"/dev/xvdj"), FilePath(b"/dev/xvdo")),
            (_expected_device(b"/dev/sdj"), _expected_device(b"/dev/sdo")),
        )

    def test_non_dev_rejected(self):
        """
        Devices not in ``/dev`` are rejected with ``ValueError``.
        """
        self.assertRaises(
            ValueError,
            _expected_device, b"/sys/block/sda",
        )

    def test_non_sdX_rejected(self):
        """
        Devices not in the ``sdX`` category are rejected with ``ValueError``.
        """
        self.assertRaises(
            ValueError,
            _expected_device, b"/dev/hda",
        )
