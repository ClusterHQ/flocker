# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for :py:class:`~twisted.python.FilePath` helpers.
"""

import errno
import stat

from hypothesis import given
from hypothesis.strategies import binary
from testtools.matchers import Equals

from ...testtools import TestCase
from ...testtools.matchers import dir_exists, file_contents, with_permissions
from ...testtools.strategies import permissions

from .. import make_directory, make_file


user_rw = stat.S_IRUSR | stat.S_IWUSR
user_rw_perms = permissions.filter(lambda x: x & user_rw == user_rw)


class MakeFileTests(TestCase):
    """
    Tests for :py:func:`make_file`.
    """

    @given(content=binary(average_size=20), perms=permissions)
    def test_make_file(self, content, perms):
        """
        ``make_file`` creates a file with the given content and permissions.
        """
        path = self.make_temporary_path()
        make_file(path, content, perms)
        self.addCleanup(path.remove)
        try:
            self.assertThat(path, with_permissions(Equals(perms)))
        finally:
            path.chmod(0600)
        self.assertThat(path, file_contents(Equals(content)))

    def test_make_file_defaults(self):
        """
        By default, ``make_file`` creates an empty file.
        """
        path = self.make_temporary_path()
        make_file(path)
        self.addCleanup(path.remove)
        self.assertThat(path, file_contents(Equals('')))


class MakeDirectoryTests(TestCase):
    """
    Tests for :py:func:`make_directory`.
    """

    def test_make_directory(self):
        """
        ``make_directory`` creates a directory at the given path.
        """
        path = self.make_temporary_path()
        make_directory(path)
        self.assertThat(path, dir_exists())

    def test_make_directory_exists(self):
        """
        If the directory exists, ``make_directory`` does nothing.
        """
        path = self.make_temporary_directory()
        make_directory(path)
        self.assertThat(path, dir_exists())

    def test_make_directory_file_exists(self):
        """
        If the file exists, ``make_directory`` raises an OSError with EEXIST.

        There is no particular reason for this exception rather than any
        other.
        """
        path = self.make_temporary_file()
        error = self.assertRaises(OSError, make_directory, path)
        self.assertThat(error.errno, Equals(errno.EEXIST))
