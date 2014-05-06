"""
Generic tests for filesystem APIs.

A "fixture" is a 1-argument callable that takes a :class:`unittest.TestCase`
instance as its first argument and returns some object to be used in a test.
"""
from __future__ import absolute_import

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase

from ..filesystems.interfaces import IFilesystemSnapshots



def makeIFilesystemSnapshotsTests(fixture):
    """
    Create a TestCase for IFilesystemSnapshots.

    :param fixture: A fixture that returns a :class:`IFilesystemSnapshots`
        provider.
    """
    class IFilesystemSnapshotsTests(TestCase):
        """
        Tests for :class:`IFilesystemSnapshotsTests`.

        These are functional tests if run against real filesystems.
        """
        def test_interface(self):
            """
            The tested object provides :class:`IFilesystemSnapshotsTests`.
            """
            fsSnapshots = fixture(self)
            self.assertTrue(verifyObject(IFilesystemSnapshots, fsSnapshots))


        def test_created(self):
            """
            Snapshots created with ``create()`` are listed in that order in
            ``list()``.
            """
            fsSnapshots = fixture(self)
            d = fsSnapshots.create(b"first")
            d.addCallback(lambda _: fsSnapshots.create(b"second"))
            d.addCallback(lambda _: fsSnapshots.list())
            d.addCallback(self.assertEqual, [b"first", b"second"])
            return d
    return IFilesystemSnapshotsTests
