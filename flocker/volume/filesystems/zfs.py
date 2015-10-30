# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
ZFS APIs.
"""

from __future__ import absolute_import

import os
import libzfs_core

from functools import wraps
from contextlib import contextmanager
from uuid import uuid4
from subprocess import call, check_call
from Queue import Queue

from characteristic import attributes, with_cmp, with_repr

from zope.interface import implementer

from eliot import Field, MessageType, Logger, write_traceback

from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.internet.endpoints import ProcessEndpoint, connectProtocol
from twisted.internet.protocol import Protocol
from twisted.internet.defer import Deferred, succeed
from twisted.internet.threads import deferToThreadPool
from twisted.internet.error import ConnectionDone, ProcessTerminated
from twisted.application.service import Service

from .errors import MaximumSizeTooSmall
from .interfaces import (
    IFilesystemSnapshots, IStoragePool, IFilesystem,
    FilesystemAlreadyExists)

from .._model import VolumeSize


class CommandFailed(Exception):
    """The ``zfs`` command failed for some reasons."""


class BadArguments(Exception):
    """The ``zfs`` command was called with incorrect arguments."""


class _AccumulatingProtocol(Protocol):
    """
    Accumulate all received bytes.
    """

    def __init__(self):
        self._result = Deferred()
        self._data = b""

    def dataReceived(self, data):
        self._data += data

    def connectionLost(self, reason):
        if reason.check(ConnectionDone):
            self._result.callback(self._data)
        elif reason.check(ProcessTerminated) and reason.value.exitCode == 1:
            self._result.errback(CommandFailed())
        elif reason.check(ProcessTerminated) and reason.value.exitCode == 2:
            self._result.errback(BadArguments())
        else:
            self._result.errback(reason)
        del self._result


class _AsyncLZC(object):
    """
    A proxy class for the asynchronous execution using a given reactor and its
    thread pool.

    Primarily this class dispatches its method calls to the functions in
    :mod:`libzfs_core`.  But it can also be used for the asynchronous execution
    of an arbitrary function.
    """

    def __init__(self, reactor):
        """
        :param reactor: the reactor that is to be used for the asynchronous
                        execution.
        """
        self._reactor = reactor
        self._cache = {}

    def callDeferred(self, func, *args, **kwargs):
        """
        This is a thin wrapper around :func:`deferToThreadPool`.

        Its primary advantage is that the reactor is already associated with
        an instance of :class:`_AsyncLZC` and :meth:`getThreadPool` is called
        to get the reactor's thread pool.
        """
        return deferToThreadPool(self._reactor, self._reactor.getThreadPool(),
                                 func, *args, **kwargs)

    def __getattr__(self, name):
        """
        Pretend that this class provides the same methods as the functions
        in :mod:`libzfs_core`.  The proxy methods execute the functions
        in the asynchronous mode using the reactor and its thread pool.
        """
        try:
            return self._cache[name]
        except KeyError:
            func = getattr(libzfs_core, name)

            @wraps(func)
            def _async_wrapper(*args, **kwargs):
                return self.callDeferred(func, *args, **kwargs)

            self._cache[name] = _async_wrapper
            return self._cache[name]


_reactor_to_alzc = {}


def _async_lzc(reactor):
    """
    Return an instance of :class:`_AsyncLZC` for the given reactor.

    :param reactor: the reactor.

    The instance gets associated with the reactor and the same instance will
    be returned for subsequent calls with the same ``reactor`` argument.
    """
    try:
        return _reactor_to_alzc[reactor]
    except KeyError:
        _reactor_to_alzc[reactor] = _AsyncLZC(reactor)
        return _reactor_to_alzc[reactor]


def ext_command(reactor, arguments):
    """
    Asynchronously run the given command-line tool with the given arguments.

    :param reactor: A ``IReactorProcess`` provider.

    :param arguments: A ``list`` of ``bytes``, the command and command-line
    arguments.

    :return: A :class:`Deferred` firing with the bytes of the result (on
        exit code 0), or errbacking with :class:`CommandFailed` or
        :class:`BadArguments` depending on the exit code (1 or 2).
    """
    endpoint = ProcessEndpoint(reactor, arguments[0], arguments,
                               os.environ)
    d = connectProtocol(endpoint, _AccumulatingProtocol())
    d.addCallback(lambda protocol: protocol._result)
    return d


def zfs_command(reactor, arguments):
    """
    Asynchronously run the ``zfs`` command-line tool with the given arguments.

    :param reactor: A ``IReactorProcess`` provider.

    :param arguments: A ``list`` of ``bytes``, command-line arguments to
    ``zfs``.

    :return: A :class:`Deferred` firing with the bytes of the result (on
        exit code 0), or errbacking with :class:`CommandFailed` or
        :class:`BadArguments` depending on the exit code (1 or 2).
    """
    return ext_command(reactor, [b"zfs"] + arguments)


_ZFS_COMMAND = Field.forTypes(
    "zfs_command", [bytes], u"The command which was run.")
_OUTPUT = Field.forTypes(
    "output", [bytes], u"The output generated by the command.")
_STATUS = Field.forTypes(
    "status", [int], u"The exit status of the command")


ZFS_ERROR = MessageType(
    "filesystem:zfs:error", [_ZFS_COMMAND, _OUTPUT, _STATUS],
    u"The zfs command signaled an error.")


@attributes(["name"])
class Snapshot(object):
    """
    A snapshot of a ZFS filesystem.

    :ivar bytes name: The name of the snapshot.
    """
    # TODO: The name should probably be a structured object of some sort,
    # not just a wrapper for bytes.
    # https://clusterhq.atlassian.net/browse/FLOC-668


def _latest_common_snapshot(some, others):
    """
    Pick the most recent snapshot that is common to two snapshot lists.

    :param list some: One ``list`` of ``Snapshot`` instances to consider,
        ordered from oldest to newest.

    :param list others: Another ``list`` of ``Snapshot`` instances to consider,
        ordered from oldest to newest.

    :return: The ``Snapshot`` instance which occurs closest to the end of both
        ``some`` and ``others`` If no ``Snapshot`` appears in both, ``None`` is
        returned.
    """
    others_set = set(others)
    for snapshot in reversed(some):
        if snapshot in others_set:
            return snapshot
    return None


@implementer(IFilesystem)
@with_cmp(["pool", "dataset"])
@with_repr(["pool", "dataset"])
class Filesystem(object):
    """A ZFS filesystem.

    For now the goal is simply not to pass bytes around when referring to a
    filesystem.  This will likely grow into a more sophisticiated
    implementation over time.
    """
    logger = Logger()

    def __init__(self, pool, dataset, mountpoint=None, size=None,
                 reactor=None):
        """
        :param pool: The filesystem's pool name, e.g. ``b"hpool"``.

        :param dataset: The filesystem's dataset name, e.g. ``b"myfs"``, or
            ``None`` for the top-level filesystem.

        :param twisted.python.filepath.FilePath mountpoint: Where the
            filesystem is mounted.

        :param VolumeSize size: The capacity information for this filesystem.
        """
        self.pool = pool
        self.dataset = dataset
        self._mountpoint = mountpoint
        self.size = size
        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor
        self._async_lzc = _async_lzc(self._reactor)

    def _exists(self):
        """
        Determine whether this filesystem exists locally.

        :return: ``True`` if there is a filesystem with this name, ``False``
            otherwise.
        """
        return libzfs_core.lzc_exists(self.name)

    def snapshots(self):
        if self._exists():
            zfs_snapshots = ZFSSnapshots(self._reactor, self)
            d = zfs_snapshots.list()
            d.addCallback(lambda snapshots:
                          [Snapshot(name=name)
                           for name in snapshots])
            return d
        return succeed([])

    @property
    def name(self):
        """The filesystem's full name, e.g. ``b"hpool/myfs"``."""
        if self.dataset is None:
            return self.pool
        return b"%s/%s" % (self.pool, self.dataset)

    def get_path(self):
        return self._mountpoint

    @contextmanager
    def reader(self, remote_snapshots=None):
        """
        Send zfs stream of contents.

        :param list remote_snapshots: ``Snapshot`` instances, ordered from
            oldest to newest, which are available on the writer.  The reader
            may generate a partial stream which relies on one of these
            snapshots in order to minimize the data to be transferred.
        """
        # The existing snapshot code uses Twisted, so we're not using it
        # in this iteration.  What's worse, though, is that it's not clear
        # if the current snapshot naming scheme makes any sense, and
        # moreover it violates abstraction boundaries. So as first pass
        # I'm just using UUIDs, and hopefully requirements will become
        # clearer as we iterate.
        snapshot = b"%s@%s" % (self.name, uuid4())
        libzfs_core.lzc_snapshot([snapshot])

        # Determine whether there is a shared snapshot which can be used as the
        # basis for an incremental send.
        local_snapshots = list(
            Snapshot(name=name) for name in
            _parse_snapshots(_do_list_snapshots(self), self)
        )

        if remote_snapshots is None:
            remote_snapshots = []

        latest_common_snapshot = _latest_common_snapshot(
            remote_snapshots, local_snapshots)
        latest_common_name = None
        if latest_common_snapshot is not None:
            latest_common_name = b"%s@%s" % (self.name,
                                             latest_common_snapshot.name)

        (rfd, wfd) = os.pipe()
        out = os.fdopen(rfd)
        queue = Queue()

        def send_and_close():
            try:
                libzfs_core.lzc_send(snapshot, latest_common_name, wfd)
            except Exception as e:
                message = ZFS_ERROR(zfs_command="lzc_send " + snapshot,
                                    output=str(e), status=e.errno)
                message.write(self.logger)
                write_traceback(self.logger)
            finally:
                os.close(wfd)
                queue.put(None)

        d = self._async_lzc.callDeferred(send_and_close)
        d.addBoth(lambda _: None)
        try:
            yield out
        finally:
            out.close()
            queue.get()

    @contextmanager
    def writer(self):
        """
        Read in zfs stream.
        """
        if self._exists():
            # If the filesystem already exists then this should be an
            # incremental data stream to up date it to a more recent snapshot.
            # If that's not the case then we're about to screw up - but that's
            # all we can handle for now.  Using existence of the filesystem to
            # determine whether the stream is incremental or not is definitely
            # a hack.  When we replace this mechanism with a proper API we
            # should make it include that information.
            #
            # If the stream is based on not-quite-the-latest
            # snapshot then we have to throw away all the snapshots newer than
            # it in order to receive the stream.  To do that you have to
            # force.
            #
            force = True
        else:
            # If the filesystem doesn't already exist then this is a complete
            # data stream.
            force = False

        (rfd, wfd) = os.pipe()
        wfile = os.fdopen(wfd, "w")
        queue = Queue()

        def recv_and_close():
            try:
                (header, c_header) = libzfs_core.receive_header(rfd)
                # drr_toname is a full snapshot name, but we need only the part
                # after '@' that we use to construct a local snapshot name.
                snapname = header['drr_toname'].split('@', 1)[1]
                snapname = self.name + '@' + snapname
                libzfs_core.lzc_receive_with_header(snapname, rfd, c_header,
                                                    force)
                success = True
            except Exception as e:
                success = False
                message = ZFS_ERROR(zfs_command="lzc_receive " + self.name,
                                    output=str(e), status=e.errno)
                message.write(self.logger)
                write_traceback(self.logger)
            finally:
                os.close(rfd)
                queue.put(success)

        d = self._async_lzc.callDeferred(recv_and_close)
        d.addBoth(lambda _: None)
        try:
            yield wfile
        finally:
            try:
                wfile.close()
            except:
                pass
            succeeded = queue.get()
            if succeeded and not force:
                # a new filesystem
                libzfs_core.lzc_set_prop(self.name, b"mountpoint",
                                         self._mountpoint.path)
                check_call([b"zfs", b"mount", self.name])


@implementer(IFilesystemSnapshots)
class ZFSSnapshots(object):
    """Manage snapshots on a ZFS filesystem."""

    def __init__(self, reactor, filesystem):
        self._reactor = reactor
        self._async_lzc = _async_lzc(self._reactor)
        self._filesystem = filesystem

    def create(self, name):
        encoded_name = b"%s@%s" % (self._filesystem.name, name)
        d = self._async_lzc.lzc_snapshot([encoded_name])
        d.addCallback(lambda _: None)
        return d

    def list(self):
        """
        List ZFS snapshots known to the volume manager.
        """
        return _list_snapshots(self._reactor, self._filesystem)


def _do_list_snapshots(filesystem):
    """
    Produce a list of snapshots of the given filesystem sorted by their
    creation order.

    :param Filesystem filesystem: The ZFS filesystem the snapshots of which to
        list.

    :return list: A ``list`` of ``bytes`` corresponding to the
        names of the snapshots.
    """
    snaps = []
    for snap in libzfs_core.lzc_list_snaps(filesystem.name):
        creation = libzfs_core.lzc_get_props(snap)[b"createtxg"]
        snaps.append((snap, creation))
    return [x[0] for x in sorted(snaps, key=lambda x: x[1])]


def _parse_snapshots(data, filesystem):
    """
    Transform the list of fully qualified snapshot names to a list of
    snapshot short names that are relative to the given filesystem.

    :param bytes data: A ``list`` of ``bytes`` corresponding to the names
        of the snapshots.

    :param Filesystem filesystem: The filesystem from which to extract
        snapshots.  If the output includes snapshots for other filesystems (eg
        siblings or children) they are excluded from the result.

    :return list: A ``list`` of ``bytes`` corresponding to the
        short names of the snapshots.  The order of the list is the
        same as the order of the snapshots in the data being parsed.
    """
    result = []
    for snap in data:
        dataset, snapshot = snap.split(b'@', 1)
        if dataset == filesystem.name:
            result.append(snapshot)
    return result


def _list_snapshots(reactor, filesystem):
    """
    List the snapshots of the given filesystem.

    :param IReactorProcess reactor: The reactor to use to launch the ``zfs``
        child process.

    :param Filesystem filesystem: The filesystem the snapshots of which to
        retrieve.

    :return: A ``Deferred`` which fires with a ``list`` of ``Snapshot``
        instances giving the requested snapshot information.
    """
    d = _async_lzc(reactor).callDeferred(_do_list_snapshots, filesystem)
    d.addCallback(_parse_snapshots, filesystem)
    return d


def volume_to_dataset(volume):
    """Convert a volume to a dataset name.

    :param flocker.volume.service.Volume volume: The volume.

    :return: Dataset name as ``bytes``.
    """
    return b"%s.%s" % (volume.node_id.encode("ascii"),
                       volume.name.to_bytes())


@implementer(IStoragePool)
@with_repr(["_name"])
@with_cmp(["_name", "_mount_root"])
class StoragePool(Service):
    """
    A ZFS storage pool.

    Remotely owned filesystems are mounted read-only to prevent changes
    (divergence which would break ``zfs recv``).  This is done by having the
    root dataset be ``readonly=on`` - which is inherited by all child datasets.
    Locally owned datasets have this overridden with an explicit
    ```readonly=off`` property set on them.
    """
    logger = Logger()

    def __init__(self, reactor, name, mount_root):
        """
        :param reactor: A ``IReactorProcess`` provider.
        :param bytes name: The pool's name.
        :param FilePath mount_root: Directory where filesystems should be
            mounted.
        """
        self._reactor = reactor
        self._async_lzc = _async_lzc(self._reactor)
        self._name = name
        self._mount_root = mount_root

    def startService(self):
        """
        Make sure that the necessary properties are set on the root Flocker zfs
        storage pool.
        """
        Service.startService(self)

        # These next things are logically part of the storage pool creation
        # process.  Since Flocker itself doesn't yet have any involvement with
        # that process, it's difficult to find a better time/place to set these
        # properties than here - ie, "every time we're about to interact with
        # the storage pool".  In the future it would be better if we could do
        # these things one-off - sometime around when the pool is created or
        # when Flocker is first installed, for example.  Then we could get rid
        # of these operations from this method (which eliminates the motivation
        # for StoragePool being an IService implementation).
        # https://clusterhq.atlassian.net/browse/FLOC-635

        # First, actually unmount the dataset.
        # See the explanation below where 'canmount' is set to 'off'.
        # At the moment all errors are ignored.
        call([b"umount", self._name])

        # Set the root dataset to be read only; IService.startService
        # doesn't support Deferred results, and in any case startup can be
        # synchronous with no ill effects.
        try:
            libzfs_core.lzc_set_prop(self._name, b"readonly", 1)
        except libzfs_core.exceptions.ZFSError as e:
            message = ZFS_ERROR(zfs_command="set readonly=on " + self._name,
                                output=str(e), status=e.errno)
            message.write(self.logger)

        # If the root dataset is read-only then it's not possible to create
        # mountpoints in it for its child datasets.  Avoid mounting it to avoid
        # this problem.  This should be fine since we don't ever intend to put
        # any actual data into the root dataset.
        try:
            libzfs_core.lzc_set_prop(self._name, b"canmount", 0)
        except libzfs_core.exceptions.ZFSError as e:
            message = ZFS_ERROR(zfs_command="set canmount=off" + self._name,
                                output=str(e), status=e.errno)
            message.write(self.logger)

    def _check_for_out_of_space(self, reason):
        """
        Translate a ZFS command failure into ``MaximumSizeTooSmall`` if that is
        what the command failure represents.
        """
        # This can't actually check anything.
        # https://clusterhq.atlassian.net/browse/FLOC-992
        return Failure(MaximumSizeTooSmall())

    def create(self, volume):
        filesystem = self.get(volume)
        mount_path = filesystem.get_path().path
        properties = {b"mountpoint": mount_path}
        if volume.locally_owned():
            properties[b"readonly"] = 0
        if volume.size.maximum_size is not None:
            properties[b"refquota"] = volume.size.maximum_size
        d = self._async_lzc.lzc_create(filesystem.name, props=properties)
        d.addErrback(self._check_for_out_of_space)
        d.addCallback(
            lambda _: zfs_command(self._reactor, [b"mount", filesystem.name]))
        d.addCallback(lambda _: filesystem)
        return d

    def destroy(self, volume):
        filesystem = self.get(volume)
        d = filesystem.snapshots()

        # It would be better to have snapshot destruction logic as part of
        # IFilesystemSnapshots, but that isn't really necessary yet.
        def got_snapshots(snapshots):
            return self._async_lzc.lzc_destroy_snaps([
                b"%s@%s" % (filesystem.name, snapshot.name)
                for snapshot in snapshots
            ], defer=False)
        d.addCallback(got_snapshots)
        d.addCallback(
            lambda _: ext_command(self._reactor, [b"umount", filesystem.name]))
        d.addCallback(
            lambda _: self._async_lzc.lzc_destroy(filesystem.name))
        return d

    def set_maximum_size(self, volume):
        filesystem = self.get(volume)
        if volume.size.maximum_size is not None:
            requota = volume.size.maximum_size
        else:
            # zero means no quota
            requota = 0
        d = self._async_lzc.lzc_set_prop(filesystem.name, b"refquota", requota)
        d.addErrback(self._check_for_out_of_space)
        d.addCallback(lambda _: filesystem)
        return d

    def clone_to(self, parent, volume):
        parent_filesystem = self.get(parent)
        new_filesystem = self.get(volume)
        zfs_snapshots = ZFSSnapshots(self._reactor, parent_filesystem)
        snapshot_name = bytes(uuid4())
        d = zfs_snapshots.create(snapshot_name)
        full_snap_name = b"%s@%s" % (parent_filesystem.name, snapshot_name)
        d.addCallback(lambda _: self._async_lzc.lzc_clone(new_filesystem.name,
                                                          full_snap_name))
        self._created(d, volume)
        d.addCallback(lambda _: new_filesystem)
        return d

    def change_owner(self, volume, new_volume):
        old_filesystem = self.get(volume)
        new_filesystem = self.get(new_volume)
        d = ext_command(self._reactor,
                        [b"umount", old_filesystem.name])
        d.addCallback(lambda _: self._async_lzc.lzc_rename(
            old_filesystem.name, new_filesystem.name))
        self._created(d, new_volume)

        def remounted(ignored):
            # Use os.rmdir instead of FilePath.remove since we don't want
            # recursive behavior. If the directory is non-empty, something
            # went wrong (or there is a race) and we don't want to lose data.
            os.rmdir(old_filesystem.get_path().path)
        d.addCallback(remounted)
        d.addCallback(lambda _: new_filesystem)
        return d

    def _created(self, result, new_volume):
        """
        Common post-processing for attempts at creating new volumes from other
        volumes.

        In particular this includes error handling and ensuring read-only
        and mountpoint properties are set correctly.

        :param Deferred result: The result of the creation attempt.

        :param Volume new_volume: Volume we're trying to create.
        """
        new_filesystem = self.get(new_volume)
        new_mount_path = new_filesystem.get_path().path

        def creation_failed(f):
            if (f.check(libzfs_core.exceptions.FilesystemExists)):
                # This isn't the only reason the operation could fail. We
                # should figure out why and report it appropriately.
                # https://clusterhq.atlassian.net/browse/FLOC-199
                raise FilesystemAlreadyExists()
            return f
        result.addErrback(creation_failed)

        def exists(ignored):
            if new_volume.locally_owned():
                result = self._async_lzc.lzc_set_prop(new_filesystem.name,
                                                      b"readonly", 0)
            else:
                result = self._async_lzc.lzc_inherit_prop(new_filesystem.name,
                                                          b"readonly")
            result.addCallback(lambda _: self._async_lzc.lzc_set_prop(
                new_filesystem.name, b"mountpoint", new_mount_path))
            result.addCallback(lambda _: zfs_command(
                self._reactor, [b"mount", new_filesystem.name]))
            return result
        result.addCallback(exists)

    def get(self, volume):
        dataset = volume_to_dataset(volume)
        mount_path = self._mount_root.child(dataset)
        return Filesystem(
            self._name, dataset, mount_path, volume.size)

    def enumerate(self):
        listing = self._async_lzc.callDeferred(_list_filesystems, self._name)

        def listed(filesystems):
            result = set()
            for entry in filesystems:
                filesystem = Filesystem(
                    self._name, entry.dataset, FilePath(entry.mountpoint),
                    VolumeSize(maximum_size=entry.refquota))
                result.add(filesystem)
            return result

        return listing.addCallback(listed)


@attributes(["dataset", "mountpoint", "refquota"], apply_immutable=True)
class _DatasetInfo(object):
    """
    :ivar bytes dataset: The name of the ZFS dataset to which this information
        relates.
    :ivar bytes mountpoint: The value of the dataset's ``mountpoint`` property
        (where it will be auto-mounted by ZFS).
    :ivar int refquota: The value of the dataset's ``refquota`` property (the
        maximum number of bytes the dataset is allowed to have a reference to).
    """


def _list_filesystems(pool):
    """Get a listing of all filesystems on a given pool.

    :param pool: A `flocker.volume.filesystems.interface.IStoragePool`
        provider.
    :return: An iterator, the elements of which are ``tuples`` containing
        the name and mountpoint of each filesystem.
    """
    for child in libzfs_core.lzc_list_children(pool):
        props = libzfs_core.lzc_get_props(child)
        name = child[len(pool) + 1:]
        refquota = props[b"refquota"]
        mountpoint = props[b"mountpoint"]
        if refquota == 0:
            refquota = None
        yield _DatasetInfo(
            dataset=name, mountpoint=mountpoint, refquota=refquota)
