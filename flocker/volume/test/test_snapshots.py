# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.snapshots`.
"""

from __future__ import absolute_import

from datetime import datetime

from pytz import UTC

from twisted.trial.unittest import SynchronousTestCase

from ..snapshots import SnapshotName


# The filesystem's name:
FILESYSTEM = b"test"


class SnapshotNameTests(SynchronousTestCase):
    """
    Tests for ``SnapshotName``.
    """
    def test_to_bytes(self):
        """
        ``SnapshotName.to_bytes()`` converts a ``SnapshotName`` to bytes.
        """
        dt = datetime(2014, 4, 30, 16, 23, 58, 123456, tzinfo=UTC)
        name = SnapshotName(dt, b"the_host")
        # We use ISO format, only without the timezone:
        self.assertEqual(name.to_bytes(),
                         b"%s_the_host" % (dt.isoformat()[:-6],))

    def test_from_bytes(self):
        """
        ``SnapshotName.from_bytes()`` converts the output of
        ``SnapshotName.to_bytes`` back into a ``SnapshotName``.
        """
        name = SnapshotName(datetime.now(UTC), b"ahost")
        self.assertEqual(SnapshotName.from_bytes(name.to_bytes()), name)

    def test_from_bytes_no_separator(self):
        """
        ``SnapshotName.from_bytes`` will raise a ``ValueError`` for bad inputs
        missing a ``b_``.
        """
        self.assertRaises(ValueError, SnapshotName.from_bytes, b"garbage")

    def test_from_bytes_bad_date(self):
        """
        ``SnapshotName.from_bytes`` will raise a ``ValueError`` for unparseable
        dates.
        """
        self.assertRaises(ValueError, SnapshotName.from_bytes,
                          b"2099-13-65T19:12:77.234236_name")
