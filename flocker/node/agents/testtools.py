# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents``.
"""

from characteristic import attributes
from fixtures import MethodFixture
from pyrsistent import PClass, field
from twisted.python.components import proxyForInterface
from twisted.python.filepath import FilePath
from zope.interface import Interface, implementer
from zope.interface.verify import verifyObject

from .cinder import (
    ICinderVolumeManager, INovaVolumeManager,
)

from ...testtools import TestCase, run_process

from .blockdevice_manager import (
    BlockDeviceManager, IBlockDeviceManager, UnmountError
)

from .shadow_bind_mounter import create_tmpfs_shadow_mount


def write_as_docker(directory, filename, content):
    """
    Write content to a file in a directory using docker volume mounts.

    Note this will also print "CONTAINER_RUNNING" to STDOUT if the container
    starts running. This can be used by callers to determine on failure if
    docker failed to start the container or if the job in the container failed
    to write the file.

    :param FilePath directory: The directory to bind mount into the container.
    :param unicode filename: The name of the file to create in the bind mount.
    :param unicode content: The content to write to the container.

    :raises flocker.testtools.ProcesError: If the docker command fails.
    """
    # The path for docker to expose within the container. Docker will bind
    # mount mountdir to this location within the container.
    container_path = FilePath('/vol')
    run_process([
        "docker",
        "run",  # Run a container.
        "--rm",  # Remove the container once it exits.
        # Bind mount the passed in directory into the container
        "-v", "%s:%s" % (directory.path, container_path.path),
        "busybox",  # Run the busybox image.
        # Use sh to echo the content into the file in the bind mount.
        "/bin/sh", "-c", "echo CONTAINER_RUNNING && echo -n %s > %s" % (
            content, container_path.child(filename).path)
    ])


class ICinderVolumeManagerTestsMixin(object):
    """
    Tests for ``ICinderVolumeManager`` implementations.
    """
    def test_interface(self):
        """
        ``client`` provides ``ICinderVolumeManager``.
        """
        self.assertTrue(verifyObject(ICinderVolumeManager, self.client))


def make_icindervolumemanager_tests(client_factory):
    """
    Build a ``TestCase`` for verifying that an implementation of
    ``ICinderVolumeManager`` adheres to that interface.
    """
    class Tests(ICinderVolumeManagerTestsMixin, TestCase):
        def setUp(self):
            super(Tests, self).setUp()
            self.client = client_factory(test_case=self)

    return Tests


class INovaVolumeManagerTestsMixin(object):
    """
    Tests for ``INovaVolumeManager`` implementations.
    """
    def test_interface(self):
        """
        ``client`` provides ``INovaVolumeManager``.
        """
        self.assertTrue(verifyObject(INovaVolumeManager, self.client))


def make_inovavolumemanager_tests(client_factory):
    """
    Build a ``TestCase`` for verifying that an implementation of
    ``INovaVolumeManager`` adheres to that interface.
    """
    class Tests(INovaVolumeManagerTestsMixin, TestCase):
        def setUp(self):
            super(Tests, self).setUp()
            self.client = client_factory(test_case=self)

    return Tests


def blockdevice_manager_fixture():
    """
    Creates a blockdevice_manager that cleans itself up during test cleanup.

    Cleanup is defined as unmounting all bind mounts, tmpfs mounts, and
    blockdevice mounts.

    :returns: A Fixture with a .obj attribute that is a blockdevice_manager.
    """
    manager = CleanupBlockDeviceManager(BlockDeviceManager())
    return MethodFixture(manager, None, manager.cleanup)


@attributes(["error"])
class CleanupError(Exception):
    """
    Wrapper for errors that might occur during cleanup, but should not stop
    cleanup. This is specifically for errors like an UnmountError which might
    occur if we are attempting to clean up a mount that was not mounted
    successfully, but we had no way of verifying that.

    :ivar error: The original error.
    """

    def __str__(self):
        return self.__repr__()


class _ICleanupOperation(Interface):
    """
    Interface for cleanup operations.
    """

    def execute(blockdevice_manager):
        """
        Perform the cleanup operation.

        :param blockdevice_manager: The :class:`IBlockDeviceManager` provider
            to use to execute the cleanup.

        :raises CleanupError: If an error occurs that does not indicate a bug
            in the code and should not stop cleanup execution.
        """


@implementer(_ICleanupOperation)
class _UnmountCleanup(PClass):
    """
    Object for cleanup by unmounting.

    :ivar FilePath path: The path to unmount.
    """
    path = field(type=FilePath)

    def execute(self, blockdevice_manager):
        try:
            blockdevice_manager.unmount(self.path)
        except UnmountError as e:
            raise CleanupError(error=e)


class CleanupBlockDeviceManager(proxyForInterface(IBlockDeviceManager)):
    """
    Proxies to another :class:`IBlockDeviceManager` provider, and records every
    created mount, symlink, etc. for cleanup later.

    This is a test helper class for tests that use
    :class:`IBlockDeviceManager`, and don't want to manually manage cleanup of
    all of the mounts and symlinks.

    Note: This does not behave precisely correct for mounted blockdevices that
    are unmounted by mount point.

    :ivar _cleanup_operations: A list of operations to perform upon cleanup in
        reverse order. These must provide :class:`_ICleanupOperation`.
    """
    def __init__(self, original):
        super(CleanupBlockDeviceManager, self).__init__(original)
        self._cleanup_operations = []

    def mount(self, blockdevice, mountpoint):
        self._cleanup_operations.append(_UnmountCleanup(path=blockdevice))
        return self.original.mount(blockdevice, mountpoint)

    def unmount(self, unmount_path):
        unmount_index = next(iter(
            -index
            for index, op in enumerate(reversed(self._cleanup_operations), 1)
            if op == _UnmountCleanup(path=unmount_path)
        ), None)
        if unmount_path is not None:
            self._cleanup_operations.pop(unmount_index)
        return self.original.unmount(unmount_path)

    def make_tmpfs_mount(self, mountpoint):
        self._cleanup_operations.append(_UnmountCleanup(path=mountpoint))
        return self.original.make_tmpfs_mount(mountpoint)

    def bind_mount(self, source_path, mountpoint):
        self._cleanup_operations.append(_UnmountCleanup(path=mountpoint))
        return self.original.bind_mount(source_path, mountpoint)

    def cleanup(self):
        """
        Perform all cleanup operations.
        """
        cleanup_errors = []
        for operation in reversed(self._cleanup_operations):
            try:
                operation.execute(self.original)
            except CleanupError as e:
                cleanup_errors.append(e)
        if cleanup_errors:
            raise cleanup_errors[0].error


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
    blockdevice_manager = test_case.useFixture(
        blockdevice_manager_fixture()).obj
    create_tmpfs_shadow_mount(result.backing_directory,
                              result.read_only_directory,
                              blockdevice_manager)
    return result
