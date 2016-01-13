# Copyright ClusterHQ Inc.  See LICENSE file for details.

from twisted.python.filepath import FilePath

from testtools.matchers import Not

from .. import TestCase
from ..matchers import (
    path_exists,
)


class PathExistsTests(TestCase):

    def test_does_not_exist(self):
        """
        If the path does not exist, path_exists does not match.
        """
        path = FilePath(self.mktemp())
        self.assertThat(path, Not(path_exists()))

    def test_file_exists(self):
        """
        If there is a file at path, path_exists matches.
        """
        path = FilePath(self.mktemp())
        path.setContent('foo')
        self.assertThat(path, path_exists())

    def test_dir_exists(self):
        """
        If there is a directory at path, path_exists matches.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        self.assertThat(path, path_exists())
