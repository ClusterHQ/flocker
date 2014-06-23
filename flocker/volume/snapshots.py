# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Drive the snapshotting of a filesystem, based on change events from elsewhere.
"""

from __future__ import absolute_import

from collections import namedtuple
from datetime import datetime

from pytz import UTC


class SnapshotName(namedtuple("SnapshotName", "timestamp node")):
    """
    A name of a snapshot.

    :ivar timestamp: The time when the snapshot was created, a
        :class:`datetime` with UTC timezone.

    :ivar node: The name of the node creating the snapshot, as ``bytes``.
    """
    # We don't use isoformat() because:
    # 1. It returns inconsistent results (it omits microseconds when
    #    they're 0).
    # 2. ZFS snapshots are not allowed to have a + in the name, so we need to
    #    omit timezone information.
    _dateFormat = b"%Y-%m-%dT%H:%M:%S.%f"

    def to_bytes(self):
        """
        Encode the snapshot name into bytes.

        :return: Snapshot name encoded into ``bytes``.
        """
        return b"%s_%s" % (self.timestamp.strftime(self._dateFormat),
                           self.node)

    @classmethod
    def from_bytes(cls, encoded):
        """
        Decode an encoded snapshot name.

        :param encoded: The output of :meth:`SnapshotName.to_bytes`.

        :return: A :class:`SnapshotName` instance decoded from the bytes.
        """
        timestamp, node = encoded.split(b"_", 1)
        timestamp = datetime.strptime(timestamp, cls._dateFormat).replace(
            tzinfo=UTC)
        return SnapshotName(timestamp, node)
