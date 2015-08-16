# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ZFS filesystem implementation.

These tests require the ability to create a new ZFS storage pool (using
``zpool``) and the ability to interact with that pool (using ``zfs``).

Further coverage is provided in
:module:`flocker.volume.test.test_filesystems_zfs`.
"""

import subprocess
import errno

from twisted.internet import reactor
from twisted.internet.task import cooperate
from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ..test.filesystemtests import (
    make_ifilesystemsnapshots_tests, make_istoragepool_tests, create_and_copy,
    copy, assertVolumesEqual,
)
from ..filesystems.errors import MaximumSizeTooSmall
from ..filesystems.zfs import (
    Snapshot, ZFSSnapshots, Filesystem, StoragePool, volume_to_dataset,
    zfs_command,
)
from ..service import Volume, VolumeName
from .._model import VolumeSize
from ..testtools import create_zfs_pool, service_for_pool


class IFilesystemSnapshotsTests(make_ifilesystemsnapshots_tests(
        lambda test_case: ZFSSnapshots(
            reactor, Filesystem(create_zfs_pool(test_case), None)))):
    """``IFilesystemSnapshots`` tests for ZFS."""


def build_pool(test_case):
    """
    Create a ``StoragePool``.

    :param TestCase test_case: The test in which this pool will exist.

    :return: A new ``StoragePool``.
    """
    return StoragePool(reactor, create_zfs_pool(test_case),
                       FilePath(test_case.mktemp()))


class IStoragePoolTests(make_istoragepool_tests(
        build_pool, lambda fs: ZFSSnapshots(reactor, fs))):
    """
    ``IStoragePoolTests`` for ZFS storage pool.
    """


MY_VOLUME = VolumeName(namespace=u"myns", dataset_id=u"myvolume")
MY_VOLUME2 = VolumeName(namespace=u"myns", dataset_id=u"myvolume2")


class VolumeToDatasetTests(TestCase):
    """Tests for ``volume_to_dataset``."""
    def test_volume_to_dataset(self):
        """``volume_to_dataset`` includes the node ID, dataset
        name and (for future functionality) a default branch name.
        """
        volume = Volume(node_id=u"my-uuid", name=MY_VOLUME, service=None)
        self.assertEqual(volume_to_dataset(volume),
                         b"my-uuid.myns.myvolume")


class StoragePoolTests(TestCase):
    """
    ZFS-specific ``StoragePool`` tests.
    """

    def test_mount_root(self):
        """Mountpoints are children of the mount root."""
        mount_root = FilePath(self.mktemp())
        mount_root.makedirs()
        pool = StoragePool(reactor, create_zfs_pool(self), mount_root)
        service = service_for_pool(self, pool)
        volume = service.get(MY_VOLUME)

        d = pool.create(volume)

        def gotFilesystem(filesystem):
            self.assertEqual(filesystem.get_path(),
                             mount_root.child(volume_to_dataset(volume)))
        d.addCallback(gotFilesystem)
        return d

    def test_filesystem_identity(self):
        """
        Filesystems are created with the correct pool and dataset names.
        """
        mount_root = FilePath(self.mktemp())
        pool_name = create_zfs_pool(self)
        pool = StoragePool(reactor, pool_name, mount_root)
        service = service_for_pool(self, pool)
        volume = service.get(MY_VOLUME)

        d = pool.create(volume)

        def gotFilesystem(filesystem):
            self.assertEqual(
                filesystem,
                Filesystem(pool_name, volume_to_dataset(volume)))
        d.addCallback(gotFilesystem)
        return d

    def test_actual_mountpoint(self):
        """
        The mountpoint of the filesystem is the actual ZFS mountpoint.
        """
        mount_root = FilePath(self.mktemp())
        pool_name = create_zfs_pool(self)
        pool = StoragePool(reactor, pool_name, mount_root)
        service = service_for_pool(self, pool)
        volume = service.get(MY_VOLUME)

        d = pool.create(volume)

        def gotFilesystem(filesystem):
            self.assertEqual(
                filesystem.get_path().path,
                subprocess.check_output(
                    [b"zfs", b"get", b"-H", b"-o", b"value",
                     b"mountpoint", filesystem.name]).strip())
        d.addCallback(gotFilesystem)
        return d

    def test_no_maximum_size(self):
        """
        The filesystem is created with no ``refquota`` property if the maximum
        size is unspecified.
        """
        mount_root = FilePath(self.mktemp())
        pool_name = create_zfs_pool(self)
        pool = StoragePool(reactor, pool_name, mount_root)
        service = service_for_pool(self, pool)
        volume = service.get(MY_VOLUME)

        d = pool.create(volume)

        def created_filesystem(filesystem):
            refquota = subprocess.check_output([
                b"zfs", b"get", b"-H", b"-o", b"value", b"refquota",
                filesystem.name]).strip()
            self.assertEqual(b"none", refquota)
        d.addCallback(created_filesystem)
        return d

    def test_maximum_size_sets_refquota(self):
        """
        The filesystem is created with a ``refquota`` property set to the value
        of the volume's maximum size if that value is not ``None``.
        """
        size = VolumeSize(maximum_size=1024 * 64)
        mount_root = FilePath(self.mktemp())
        pool_name = create_zfs_pool(self)
        pool = StoragePool(reactor, pool_name, mount_root)
        service = service_for_pool(self, pool)
        volume = service.get(MY_VOLUME, size=size)

        d = pool.create(volume)

        def created_filesystem(filesystem):
            refquota = subprocess.check_output([
                b"zfs", b"get",
                # Skip displaying the header
                b"-H",
                # Display machine-parseable (exact) values
                b"-p",
                # Output only the value
                b"-o", b"value",
                # Get the value of the refquota property
                b"refquota",
                # For this filesystem
                filesystem.name]).decode("ascii").strip()
            if refquota == u"none":
                refquota = None
            else:
                refquota = int(refquota)
            self.assertEqual(size.maximum_size, refquota)
        d.addCallback(created_filesystem)
        return d

    def test_change_owner_does_not_remove_non_empty_mountpoint(self):
        """
        ``StoragePool.change_owner()`` doesn't delete the contents of the
        original mountpoint, if it is non-empty.

        ZFS doesn't like to mount volumes over non-empty directories. To test
        this, we change the original mount to be a legacy mount (mounted using
        manpage:`mount(8)`).
        """
        pool = StoragePool(reactor, create_zfs_pool(self),
                           FilePath(self.mktemp()))
        service = service_for_pool(self, pool)
        volume = service.get(MY_VOLUME)
        new_volume = Volume(node_id=u"other-uuid", name=MY_VOLUME2,
                            service=service)
        original_mount = volume.get_filesystem().get_path()
        d = pool.create(volume)

        def created_filesystems(ignored):
            filesystem_name = volume.get_filesystem().name
            subprocess.check_call(['zfs', 'unmount', filesystem_name])
            # Create a file hiding under the original mount point
            original_mount.child('file').setContent('content')
            # Remount the volume at the original mount point as a legacy mount.
            subprocess.check_call(['zfs', 'set', 'mountpoint=legacy',
                                   filesystem_name])
            subprocess.check_call(['mount', '-t', 'zfs', filesystem_name,
                                   original_mount.path])
            return pool.change_owner(volume, new_volume)
        d.addCallback(created_filesystems)

        self.assertFailure(d, OSError)

        def changed_owner(filesystem):
            self.assertEqual(original_mount.child('file').getContent(),
                             b'content')
        d.addCallback(changed_owner)
        return d

    def test_locally_owned_created_writeable(self):
        """
        A filesystem which is created for a locally owned volume is writeable.
        """
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        volume = service.get(MY_VOLUME)

        d = pool.create(volume)

        def created_filesystems(filesystem):
            # This would error if writing was not possible:
            filesystem.get_path().child(b"text").setContent(b"hello")
        d.addCallback(created_filesystems)
        return d

    def assertReadOnly(self, path):
        """
        Assert writes are not possible to the given filesystem path.

        :param FilePath path: Directory which ought to be read-only.
        """
        exc = self.assertRaises(OSError,
                                path.child(b"text").setContent, b"hello")
        self.assertEqual(exc.args[0], errno.EROFS)

    def test_remotely_owned_created_readonly(self):
        """
        A filesystem which is created for a remotely owned volume is not
        writeable.
        """
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        volume = Volume(node_id=u"remoteone", name=MY_VOLUME, service=service)

        d = pool.create(volume)

        def created_filesystems(filesystem):
            self.assertReadOnly(filesystem.get_path())
        d.addCallback(created_filesystems)
        return d

    def test_locally_owned_cloned_writeable(self):
        """
        A filesystem which is cloned into a locally owned volume is writeable.
        """
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        parent = service.get(MY_VOLUME2)
        volume = service.get(MY_VOLUME)

        d = pool.create(parent)
        d.addCallback(lambda _: pool.clone_to(parent, volume))

        def created_filesystems(filesystem):
            # This would error if writing was not possible:
            filesystem.get_path().child(b"text").setContent(b"hello")
        d.addCallback(created_filesystems)
        return d

    def test_remotely_owned_cloned_readonly(self):
        """
        A filesystem which is cloned into a remotely owned volume is not
        writeable.
        """
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        parent = service.get(MY_VOLUME2)
        volume = Volume(node_id=u"remoteone", name=MY_VOLUME, service=service)

        d = pool.create(parent)
        d.addCallback(lambda _: pool.clone_to(parent, volume))

        def created_filesystems(filesystem):
            self.assertReadOnly(filesystem.get_path())
        d.addCallback(created_filesystems)
        return d

    def test_written_created_readonly(self):
        """
        A filesystem which is received from a remote filesystem (which is
        writable in its origin pool) is not writeable.
        """
        d = create_and_copy(self, build_pool)

        def got_volumes(copied):
            self.assertReadOnly(copied.to_volume.get_filesystem().get_path())
        d.addCallback(got_volumes)
        return d

    def test_owner_change_to_locally_becomes_writeable(self):
        """
        A filesystem which was previously remotely owned and is now locally
        owned becomes writeable.
        """
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        local_volume = service.get(MY_VOLUME)
        remote_volume = Volume(node_id=u"other-uuid", name=MY_VOLUME2,
                               service=service)

        d = pool.create(remote_volume)

        def created_filesystems(ignored):
            return pool.change_owner(remote_volume, local_volume)
        d.addCallback(created_filesystems)

        def changed_owner(filesystem):
            # This would error if writing was not possible:
            filesystem.get_path().child(b"text").setContent(b"hello")
        d.addCallback(changed_owner)
        return d

    def test_owner_change_to_remote_becomes_readonly(self):
        """
        A filesystem which was previously locally owned and is now remotely
        owned becomes unwriteable.
        """
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        local_volume = service.get(MY_VOLUME)
        remote_volume = Volume(node_id=u"other-uuid", name=MY_VOLUME2,
                               service=service)

        d = pool.create(local_volume)

        def created_filesystems(ignored):
            return pool.change_owner(local_volume, remote_volume)
        d.addCallback(created_filesystems)

        def changed_owner(filesystem):
            self.assertReadOnly(filesystem.get_path())
        d.addCallback(changed_owner)
        return d

    def test_write_update_to_changed_filesystem(self):
        """
        Writing an update of the contents of one pool's filesystem to
        another pool's filesystem that was previously created this way and
        was since changed drops any changes and updates its contents to
        the sender's.
        """
        d = create_and_copy(self, build_pool)

        def got_volumes(copied):
            from_volume, to_volume = copied.from_volume, copied.to_volume

            # Mutate the second volume's filesystem:
            to_filesystem = to_volume.get_filesystem()
            subprocess.check_call([b"zfs", b"set", b"readonly=off",
                                   to_filesystem.name])

            to_path = to_filesystem.get_path()
            to_path.child(b"extra").setContent(b"lalala")

            # Writing from first volume to second volume should revert
            # any changes to the second volume:
            from_path = from_volume.get_filesystem().get_path()
            from_path.child(b"anotherfile").setContent(b"hello")
            from_path.child(b"file").remove()

            copying = copy(from_volume, to_volume)

            def copied(ignored):
                assertVolumesEqual(self, from_volume, to_volume)
            copying.addCallback(copied)
            return copying
        d.addCallback(got_volumes)
        return d


class IncrementalPushTests(TestCase):
    """
    Tests for incremental push based on ZFS snapshots.
    """
    def test_less_data(self):
        """
        Fewer bytes are available from ``Filesystem.reader`` when the reader
        and writer are found to share a snapshot.
        """
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        volume = service.get(MY_VOLUME)
        creating = pool.create(volume)

        def created(filesystem):
            # Save it for later use.
            self.filesystem = filesystem

            # Put some data onto the volume so there is a baseline against
            # which to compare.
            path = filesystem.get_path()
            path.child(b"some-data").setContent(b"hello world" * 1024)

            # TODO: Snapshots are created implicitly by `reader`.  So abuse
            # that fact to get a snapshot.  An incremental send based on this
            # snapshot will be able to exclude the data written above.
            # Ultimately it would be better to have an API the purpose of which
            # is explicitly to take a snapshot and to use that here instead of
            # relying on `reader` to do this.
            with filesystem.reader() as reader:
                # Capture the size of this stream for later comparison.
                self.complete_size = len(reader.read())

            # Capture the snapshots that exist now so they can be given as an
            # argument to the reader method.
            snapshots = filesystem.snapshots()
            return snapshots

        loading = creating.addCallback(created)

        def loaded(snapshots):
            # Perform another send, supplying snapshots available on the writer
            # so an incremental stream can be constructed.

            with self.filesystem.reader(snapshots) as reader:
                incremental_size = len(reader.read())

            self.assertTrue(
                incremental_size < self.complete_size,
                "Bytes of data for incremental send ({}) was not fewer than "
                "bytes of data for complete send ({}).".format(
                    incremental_size, self.complete_size)
            )

        loading.addCallback(loaded)
        return loading


class FilesystemTests(TestCase):
    """
    ZFS-specific tests for ``Filesystem``.
    """
    def test_snapshots(self):
        """
        The ``Deferred`` returned by ``Filesystem.snapshots`` fires with a
        ``list`` of ``Snapshot`` instances corresponding to the snapshots that
        exist for the ZFS filesystem to which the ``Filesystem`` instance
        corresponds.
        """
        expected_names = [b"foo", b"bar"]

        # Create a filesystem and a couple snapshots.
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        volume = service.get(MY_VOLUME)
        creating = pool.create(volume)

        def created(filesystem):
            # Save it for later.
            self.filesystem = filesystem

            # Take a couple snapshots now that there is a filesystem.
            return cooperate(
                zfs_command(
                    reactor, [
                        b"snapshot",
                        u"{}@{}".format(filesystem.name, name).encode("ascii"),
                    ]
                )
                for name in expected_names
            ).whenDone()

        snapshotting = creating.addCallback(created)

        def snapshotted(ignored):
            # Now that some snapshots exist, interrogate the system.
            return self.filesystem.snapshots()

        loading = snapshotting.addCallback(snapshotted)

        def loaded(snapshots):
            self.assertEqual(
                list(Snapshot(name=name) for name in expected_names),
                snapshots)

        loading.addCallback(loaded)
        return loading

    def test_maximum_size_too_small(self):
        """
        If the maximum size specified for filesystem creation is smaller than
        the storage pool allows, ``MaximumSizeTooSmall`` is raised.
        """
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        # This happens to be too small for any ZFS filesystem.
        volume = service.get(MY_VOLUME, size=VolumeSize(maximum_size=10))
        creating = pool.create(volume)
        return self.assertFailure(creating, MaximumSizeTooSmall)

    def test_maximum_size_enforced(self):
        """
        The maximum size specified for a filesystem is enforced by the ZFS
        implementation.  Attempts to write more data than the maximum size
        fail.
        """
        pool = build_pool(self)
        service = service_for_pool(self, pool)
        # 40 MiB is an arbitrary value for the maximum size which is
        # sufficiently smaller than the current test pool size of 100 MiB.
        # Note that at the moment the usable pool size (minus the internal
        # data and reservations) is about 60 MiB.
        maximum_size = 40 * 1024 * 1024
        volume = service.get(
            MY_VOLUME, size=VolumeSize(maximum_size=maximum_size))
        creating = pool.create(volume)

        def created(filesystem):
            path = filesystem.get_path()
            # Try to write one byte more than the maximum_size of data.
            with path.child(b"ok").open("w") as fObj:
                chunk_size = 8 * 1024
                chunk = b"x" * chunk_size
                for i in range(maximum_size / chunk_size):
                    fObj.write(chunk)
                fObj.flush()
                with self.assertRaises(IOError) as ctx:
                    fObj.write(b"x")
                    fObj.flush()
                self.assertEqual(ctx.exception.args[0], errno.EDQUOT)

        creating.addCallback(created)
        return creating
