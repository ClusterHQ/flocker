# Copyright ClusterHQ Inc.  See LICENSE file for details.

from uuid import uuid4

from twisted.python.filepath import FilePath
from testtools.matchers import Not, FileExists, Equals

from ....testtools import TestCase, ProcessError
from ...testtools import if_docker_configured
from ..testtools import blockdevice_manager_fixture, write_as_docker
from ..blockdevice_manager import Permissions

from ..shadow_bind_mounter import create_tmpfs_shadow_mount, is_shadow_mount


class CreateShadowMountTests(TestCase):
    """
    Tests for :func:`create_tmpfs_shadow_mount`.
    """

    def setUp(self):
        super(CreateShadowMountTests, self).setUp()
        self._blockdevice_manager = self.useFixture(
            blockdevice_manager_fixture()).obj

    def _make_dir(self):
        """
        Create a new temporary directory.

        :returns FilePath: The filepath to the newly created directory.
        """
        directory = FilePath(self.mktemp())
        return directory

    def test_is_shadow_mount_fails_if_rw(self):
        """
        ``is_shadow_mount`` returns False if the read-only part of the shadow
        mount is mounted read-write.
        """
        ro_dir = self._make_dir()
        backing_directory = self._make_dir()
        backing_directory.makedirs()
        ro_dir.makedirs()
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(False),
                        'Incorrectly found directories to be shadows.')
        create_tmpfs_shadow_mount(backing_directory,
                                  ro_dir,
                                  self._blockdevice_manager)
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(True),
                        'Did not determine shadow directories to be shadows.')
        self._blockdevice_manager.remount(ro_dir, Permissions.READ_WRITE)
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(False),
                        'Found shadow directories despite RO half being RW.')

    def test_is_shadow_mount_children(self):
        """
        ``is_shadow_mount`` returns True when directories are subdirectories in
        shadow_mounts.
        """
        ro_dir = self._make_dir().child('subdir')
        backing_directory = self._make_dir().child('subdir')
        backing_directory.makedirs()
        ro_dir.makedirs()
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(False),
                        'Incorrectly found directories to be shadows.')
        create_tmpfs_shadow_mount(backing_directory.parent(),
                                  ro_dir.parent(),
                                  self._blockdevice_manager)
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(True),
                        'Did not determine shadow directories to be shadows.')

    def test_is_shadow_mount_null(self):
        """
        ``is_shadow_mount`` returns False when directories do not exist or are
        not directories.
        """
        ro_dir = self._make_dir().child('subdir')
        backing_directory = self._make_dir().child('subdir')
        backing_directory.parent().makedirs()
        ro_dir.parent().makedirs()
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(False),
                        'Incorrectly found directories to be shadows.')
        create_tmpfs_shadow_mount(backing_directory.parent(),
                                  ro_dir.parent(),
                                  self._blockdevice_manager)
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(False),
                        'Found non-existent directories to be shadows.')
        backing_directory.makedirs()
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(True),
                        'Did not determine valid shadows to be shadows.')
        backing_directory.remove()
        backing_directory.touch()
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(False),
                        'Found non-directories to be shadows.')

    def test_can_determine_shadow_mount(self):
        """
        ``is_shadow_mount`` can detect when a shadow mount is created.
        """
        ro_dir = self._make_dir()
        backing_directory = self._make_dir()
        backing_directory.makedirs()
        ro_dir.makedirs()
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(False),
                        'Incorrectly found directories to be shadows.')
        create_tmpfs_shadow_mount(backing_directory,
                                  ro_dir,
                                  self._blockdevice_manager)
        self.expectThat(is_shadow_mount(backing_directory, ro_dir,
                                        self._blockdevice_manager),
                        Equals(True),
                        'Did not determine shadow directories to be shadows.')

    def test_can_determine_which_directories_are_linked(self):
        """
        ``is_shadow_mount`` can detect when a shadow mount is created.
        """
        ro_dirs = list(self._make_dir() for _ in xrange(2))
        backing_dirs = list(self._make_dir() for _ in xrange(2))
        for directory in ro_dirs + backing_dirs:
            directory.makedirs()
        for ro_dir, backing_dir in zip(ro_dirs, backing_dirs):
            create_tmpfs_shadow_mount(backing_dir,
                                      ro_dir,
                                      self._blockdevice_manager)
        # The crossed directories should not be reported as being shadow
        # mounts.
        for ro_dir, backing_dir in zip(ro_dirs, reversed(backing_dirs)):
            self.expectThat(is_shadow_mount(backing_dir, ro_dir,
                                            self._blockdevice_manager),
                            Equals(False),
                            'Incorrectly found directories of different roots '
                            'to be shadows.')
        # The correctly paired directories should be reported as being shadow
        # mounts.
        for ro_dir, backing_dir in zip(ro_dirs, backing_dirs):
            self.expectThat(is_shadow_mount(backing_dir, ro_dir,
                                            self._blockdevice_manager),
                            Equals(True),
                            'Failed to identify directories as shadows.')

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
