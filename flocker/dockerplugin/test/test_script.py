# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Unit tests for the Docker plugin script.
"""

from twisted.python.filepath import FilePath

from ...testtools import TestCase
from .._script import DockerPluginScript


class DockerPluginScriptTests(TestCase):
    """
    Tests for ``DockerPluginScript``.
    """
    def test_creates_directory_if_missing(self):
        """
        If the directory where the Docker plugin listens on Unix socket does
        not exist, the plugin will create it.
        """
        path = FilePath(self.mktemp())
        DockerPluginScript()._create_listening_directory(path)
        self.assertTrue(path.exists())

    def test_no_failure_if_directory_exists(self):
        """
        If the directory where the Docker plugin listens on Unix socket does
        exist, the plugin will not complain.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        DockerPluginScript()._create_listening_directory(path)
        self.assertTrue(path.exists())

    def test_permissions(self):
        """
        The directory is created with restrictive permissions.
        """
        path = FilePath(self.mktemp())
        DockerPluginScript()._create_listening_directory(path)
        path.restat()
        self.assertEqual(path.getPermissions().shorthand(), "rwx------")
