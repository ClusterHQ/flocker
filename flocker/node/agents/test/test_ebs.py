# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.ebs``.
"""

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase

from ..ebs import AttachedUnexpectedDevice


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

