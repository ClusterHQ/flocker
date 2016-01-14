# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for :py:class:`~twisted.python.FilePath` helpers.
"""

import stat

from hypothesis import given
from hypothesis.strategies import binary
from testtools.matchers import Equals

from ...testtools import TestCase
from ...testtools.matchers import file_contents, with_permissions
from ...testtools.strategies import permissions

from .. import make_file


user_rw = stat.S_IRUSR | stat.S_IWUSR
user_rw_perms = permissions.filter(lambda x: x & user_rw == user_rw)


class MakeFileTests(TestCase):
    """
    Tests for :py:func:`make_file`.
    """

    @given(content=binary(average_size=20), permissions=permissions)
    def test_make_file(self, content, permissions):
        """
        ``make_file`` creates a file with the given content and permissions.
        """
        path = self.make_temporary_path()
        make_file(path, content, permissions)
        self.addCleanup(path.remove)
        self.expectThat(path, with_permissions(Equals(permissions)))
        path.chmod(0600)
        self.assertThat(path, file_contents(Equals(content)))
