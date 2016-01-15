# Copyright ClusterHQ Inc.  See LICENSE file for details.

from uuid import uuid4

from twisted.python.filepath import FilePath
from testtools.matchers import Not, FileExists

from ....testtools import TestCase, ProcessError
from ...testtools import if_docker_configured
from ..testtools import blockdevice_manager_fixture, write_as_docker

from ..shadow_bind_mounter import create_tmpfs_shadow_mount


class CreateShadowMountTests(TestCase):
    """
    Tests for :func:`create_tmpfs_shadow_mount`.
    """

    def setUp(self):
        super(CreateShadowMountTests, self).setUp()
        self._blockdevice_manager = self.useFixture(
            blockdevice_manager_fixture(self)).obj

    def _make_dir(self):
        """
        Create a new temporary directory.

        :returns FilePath: The filepath to the newly created directory.
        """
        directory = FilePath(self.mktemp())
        return directory

    def test_cannot_write_in_read_only(self):
        """
        The read only directory in the tmpfs shadow mount is not writable.
        """
        ro_dir = self._make_dir()
        create_tmpfs_shadow_mount(self._make_dir(),
                                  ro_dir,
                                  self._blockdevice_manager)
        self.assertRaises(OSError, ro_dir.child('file').touch)

    def test_changes_in_backing_directory_reflected(self):
        """
        Writes to the backing directory are reflected in the read only
        directory.
        """
        backing_directory = self._make_dir()
        ro_dir = self._make_dir()
        backing_directory.makedirs()
        ro_dir.makedirs()
        content = unicode(uuid4())
        filename = unicode(uuid4())
        write_file = backing_directory.child(filename)
        read_file = ro_dir.child(filename)
        create_tmpfs_shadow_mount(backing_directory,
                                  ro_dir,
                                  self._blockdevice_manager)
        write_file.setContent(content)
        self.assertEquals(read_file.getContent(), content)

    @if_docker_configured
    def test_docker_cant_write(self):
        """
        Docker is not able to create a volume mount inside the read only
        directory.
        """
        ro_dir = self._make_dir()
        create_tmpfs_shadow_mount(self._make_dir(),
                                  ro_dir,
                                  self._blockdevice_manager)
        content = unicode(uuid4())
        self.assertRaises(
            ProcessError,
            lambda: write_as_docker(ro_dir.child('mount'), 'file', content))
        self.assertFalse(ro_dir.child('mount').exists())

    def test_cleared_on_unmount(self):
        """
        The shadow backing directory is cleared when it is unmounted.
        """
        backing_directory = self._make_dir()
        ro_dir = self._make_dir()
        backing_directory.makedirs()
        ro_dir.makedirs()
        content = unicode(uuid4())
        filename = unicode(uuid4())
        write_file = backing_directory.child(filename)
        read_file = ro_dir.child(filename)
        create_tmpfs_shadow_mount(backing_directory,
                                  ro_dir,
                                  self._blockdevice_manager)
        write_file.setContent(content)
        self.assertEquals(read_file.getContent(), content)
        self._blockdevice_manager.unmount(ro_dir)
        self._blockdevice_manager.unmount(backing_directory)
        self.assertThat(write_file.path, Not(FileExists()))
        self.assertThat(read_file.path, Not(FileExists()))
