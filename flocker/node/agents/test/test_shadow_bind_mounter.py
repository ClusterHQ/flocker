# Copyright ClusterHQ Inc.  See LICENSE file for details.

from uuid import uuid4

from twisted.python.filepath import FilePath

from ....testtools import TestCase, run_process, _CalledProcessError
from ...testtools import if_docker_configured
from .test_blockdevice_manager import blockdevice_manager_for_test

from ..shadow_bind_mounter import create_tmpfs_shadow_mount


def write_as_docker(directory, filename, content):
    """
    Write content to a file in a directory using docker volume mounts.

    :param FilePath directory: The directory to bind mount into the container.
    :param unicode filename: The name of the file to create in the bind mount.
    :param unicode content: The content to write to the container.
    """
    container_path = FilePath('/vol')
    run_process([
        "docker",
        "run",  # Run a container.
        "--rm",  # Remove the container once it exits.
        # Bind mount the passed in directory into the container
        "-v", "%s:%s" % (directory.path, container_path.path),
        "busybox",  # Run the busybox image.
        # Use sh to echo the content into the file in the bind mount.
        "/bin/sh", "-c", "echo -n %s > %s" % (
            content, container_path.child(filename).path)
    ])


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
            _CalledProcessError,
            lambda: write_as_docker(ro_dir.child('mount'), 'file', content))
        self.assertFalse(ro_dir.child('mount').exists())
