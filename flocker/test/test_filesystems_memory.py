"""
Tests for :module:``flocker.filesystems.memory``.
"""

from __future__ import absolute_import

from twisted.internet.defer import succeed

from .filesystemtests import makeIFilesystemSnapshotsTests
from ..filesystems.memory import MemoryFilesystemSnapshots


IFilesystemSnapshotsTests = makeIFilesystemSnapshotsTests(
    lambda testCase: MemoryFilesystemSnapshots([succeed(None), succeed(None)]))
