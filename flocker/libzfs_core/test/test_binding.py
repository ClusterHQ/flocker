# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for ``libzfs_core._binding``.
"""

from __future__ import absolute_import

from os import urandom
from os.path import abspath
from unittest import TestCase
from subprocess import check_call, check_output

from .._binding import LibZFSCore

MINIMUM_SIZE = 1024 * 1024 * 64

class SendFlagsTests(TestCase):
    """
    Tests for ``LibZFSCore.LZC_SEND_FLAG_*``.
    """
    def setUp(self):
        self.lib = LibZFSCore()

    def test_integer(self):
        """
        The the send flags have type ``int``.
        """
        self.assertIsInstance(self.lib.LZC_SEND_FLAG_EMBED_DATA, int)


class CreateTests(TestCase):
    """
    Tests for ``LibZFSCore.lzc_create``.
    """
    def setUp(self):
        self.lib = LibZFSCore()
        self.pool_name = b"lzctest-" + urandom(4).encode("hex")
        vdev_name = abspath(self.pool_name + b".vdev")
        with open(vdev_name, "wb") as vdev:
            vdev.write(b"\0" * MINIMUM_SIZE)
        check_call([b"zpool", b"create", self.pool_name, vdev_name])

    def test_nul_exception(self):
        """
        If a name containing ``\\0`` is passed to ``lzc_create`` then
        ``TypeError`` is raised.
        """
        self.assertRaises(
            TypeError, self.lib.lzc_create,
            b"invalid\0name", self.lib.DMU_OST_NONE, [])

    def test_invalid_type_value(self):
        """
        If the integer passed to ``lzc_create`` is not one of the allowed
        ``DMU_OST_*`` values then ``ValueError`` is raised.
        """
        self.assertRaises(
            ValueError, self.lib.lzc_create,
            b"valid name", self.lib.DMU_OST_NUMTYPES + 1, [])

    def test_invalid_type_type(self):
        """
        If the value passed to ``lzc_create`` is not even an integer then
        ``ValueError`` is raised.
        """
        self.assertRaises(
            ValueError, self.lib.lzc_create,
            b"valid name", {}, [])

    def test_created(self):
        """
        ``lzc_create`` creates a new ZFS filesystem with the given name.
        """
        self.lib.lzc_create(self.pool_name + b"/test_created", [], [])
        names = check_output([
            b"zfs", b"list",
            # Without a header
            b"-H",
            # Names only
            b"-o", b"name",
            ])
        self.assertIn(self.pool_name + b"/test_created", names)
