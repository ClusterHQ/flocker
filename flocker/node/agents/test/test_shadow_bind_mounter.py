# Copyright ClusterHQ Inc.  See LICENSE file for details.

from uuid import uuid4

from pyrsistent import PClass, field
from twisted.python.filepath import FilePath

from ....testtools import TestCase
from .test_blockdevice_manager import blockdevice_manager_for_test

from ..shadow_bind_mounter import create_tmpfs_shadow_mount


class TestTmpfsShadowMount(PClass):
    """
    Return value type for :func:`create_tmpfs_shadow_mount_for_test`.

    :ivar FilePath backing_directory: The backing_directory for the tmpfs
        shadow mount.
    :ivar FilePath read_only_directory: The read only directory for the tmpfs
        shadow mount.
    """
    backing_directory = field(type=FilePath)
    read_only_directory = field(type=FilePath)


def create_tmpfs_shadow_mount_for_test(test_case):
    """
    Create a tmpfs shadow mount that will be cleaned up at the end of the test.

    :param TestCase test_case: The test case to use to add the addCleanup
        callbacks to.

    :returns TestTmpfsShadowMount: A nice wrapper object with the backing
        directory and the read only directory of the tmpfs shadow mount.
    """
    result = TestTmpfsShadowMount(
        backing_directory=FilePath(test_case.mktemp()),
        read_only_directory=FilePath(test_case.mktemp()),
    )
    test_case.addCleanup(result.backing_directory.remove)
    test_case.addCleanup(result.read_only_directory.remove)
    blockdevice_manager = blockdevice_manager_for_test(test_case)
    create_tmpfs_shadow_mount(result.backing_directory,
                              result.read_only_directory,
                              blockdevice_manager)
    return result


class CreateShadowMountTests(TestCase):
    """
    Tests for :func:`create_tmpfs_shadow_mount`.
    """

    def setUp(self):
        super(CreateShadowMountTests, self).setUp()
        self._blockdevice_manager = blockdevice_manager_for_test(self)

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
