# -*- test-case-name: flocker.node.agents.test.test_blockdevice -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
A loopback implementation of the ``IBlockDeviceAPI`` for testing.
"""
from uuid import UUID, uuid4
from subprocess import check_output

from zope.interface import implementer

from twisted.python.filepath import FilePath

from .blockdevice import (
    BlockDeviceVolume,
    IBlockDeviceAPI,
    UnknownInstanceID,
    AlreadyAttachedVolume,
    UnattachedVolume,
    allocated_size,
    get_blockdevice_volume,
)


def _blockdevicevolume_from_dataset_id(dataset_id, size,
                                       attached_to=None):
    """
    Create a new ``BlockDeviceVolume`` with a ``blockdevice_id`` derived
    from the given ``dataset_id``.

    This is for convenience of implementation of the loopback backend (to
    avoid needing a separate data store for mapping dataset ids to block
    device ids and back again).

    Parameters accepted have the same meaning as the attributes of
    ``BlockDeviceVolume``.
    """
    return BlockDeviceVolume(
        size=size, attached_to=attached_to,
        dataset_id=dataset_id, blockdevice_id=u"block-{0}".format(dataset_id),
    )


def _blockdevicevolume_from_blockdevice_id(blockdevice_id, size,
                                           attached_to=None):
    """
    Create a new ``BlockDeviceVolume`` with a ``dataset_id`` derived from
    the given ``blockdevice_id``.

    This reverses the transformation performed by
    ``_blockdevicevolume_from_dataset_id``.

    Parameters accepted have the same meaning as the attributes of
    ``BlockDeviceVolume``.
    """
    # Strip the "block-" prefix we added.
    dataset_id = UUID(blockdevice_id[6:])
    return BlockDeviceVolume(
        size=size, attached_to=attached_to,
        dataset_id=dataset_id,
        blockdevice_id=blockdevice_id,
    )


def _losetup_list_parse(output):
    """
    Parse the output of ``losetup --all`` which varies depending on the
    privileges of the user.

    :param unicode output: The output of ``losetup --all``.
    :returns: A ``list`` of
        2-tuple(FilePath(device_file), FilePath(backing_file))
    """
    devices = []
    for line in output.splitlines():
        parts = line.split(u":", 2)
        if len(parts) != 3:
            continue
        device_file, attributes, backing_file = parts
        device_file = FilePath(device_file.strip().encode("utf-8"))

        # Trim everything from the first left bracket, skipping over the
        # possible inode number which appears only when run as root.
        left_bracket_offset = backing_file.find(b"(")
        backing_file = backing_file[left_bracket_offset + 1:]

        # Trim everything from the right most right bracket
        right_bracket_offset = backing_file.rfind(b")")
        backing_file = backing_file[:right_bracket_offset]

        # Trim a possible embedded deleted flag
        expected_suffix_list = [b"(deleted)"]
        for suffix in expected_suffix_list:
            offset = backing_file.rfind(suffix)
            if offset > -1:
                backing_file = backing_file[:offset]

        # Remove the space that may have been between the path and the deleted
        # flag.
        backing_file = backing_file.rstrip()
        backing_file = FilePath(backing_file.encode("utf-8"))
        devices.append((device_file, backing_file))
    return devices


def _losetup_list():
    """
    List all the loopback devices on the system.

    :returns: A ``list`` of
        2-tuple(FilePath(device_file), FilePath(backing_file))
    """
    output = check_output(
        ["losetup", "--all"]
    ).decode('utf8')
    return _losetup_list_parse(output)


def _device_for_path(expected_backing_file):
    """
    :param FilePath backing_file: A path which may be associated with a
        loopback device.
    :returns: A ``FilePath`` to the loopback device if one is found, or
        ``None`` if no device exists.
    """
    for device_file, backing_file in _losetup_list():
        if expected_backing_file == backing_file:
            return device_file


def check_allocatable_size(allocation_unit, requested_size):
    """
    :param int allocation_unit: The interval in ``bytes`` to which
        ``requested_size`` will be rounded up.
    :param int requested_size: The size in ``bytes`` that is required.
    :raises: ``ValueError`` unless ``requested_size`` is exactly
        divisible by ``allocation_unit``.
    """
    actual_size = allocated_size(allocation_unit, requested_size)
    if requested_size != actual_size:
        raise ValueError(
            'Requested size {!r} is not divisible by {!r}'.format(
                requested_size, allocation_unit
            )
        )


DEFAULT_LOOPBACK_PATH = '/var/lib/flocker/loopback'


def _backing_file_name(volume):
    """
    :param BlockDeviceVolume: The volume for which to generate a
        loopback file name.
    :returns: A filename containing the encoded
        ``volume.blockdevice_id`` and ``volume.size``.
    """
    return volume.blockdevice_id.encode('ascii') + '_' + bytes(volume.size)


@implementer(IBlockDeviceAPI)
class LoopbackBlockDeviceAPI(object):
    """
    A simulated ``IBlockDeviceAPI`` which creates loopback devices backed by
    files located beneath the supplied ``root_path``.
    """
    _attached_directory_name = 'attached'
    _unattached_directory_name = 'unattached'

    def __init__(self, root_path, compute_instance_id, allocation_unit=None):
        """
        :param FilePath root_path: The path beneath which all loopback backing
            files and their organising directories will be created.
        :param unicode compute_instance_id: An identifier to use to identify
            "this" node amongst a collection of users of the same loopback
            storage area.  Instances which are meant to behave as though they
            are running on a separate node from each other should have
            different ``compute_instance_id``.
        :param int allocation_unit: The size (in bytes) that will be
            reported by ``allocation_unit``. Default is ``1``.
        """
        self._root_path = root_path
        self._compute_instance_id = compute_instance_id
        if allocation_unit is None:
            allocation_unit = 1
        self._allocation_unit = allocation_unit

    @classmethod
    def from_path(
            cls, root_path=DEFAULT_LOOPBACK_PATH, compute_instance_id=None,
            allocation_unit=None):
        """
        :param bytes root_path: The path to a directory in which loop back
            backing files will be created.  The directory is created if it does
            not already exist.
        :param compute_instance_id: See ``__init__``.  Additionally, if not
            given, a new random id will be generated.
        :param int allocation_unit: The size (in bytes) that will be
            reported by ``allocation_unit``. Default is ``1``.

        :returns: A ``LoopbackBlockDeviceAPI`` with the supplied ``root_path``.
        """
        if compute_instance_id is None:
            # If no compute_instance_id provided, invent one.
            compute_instance_id = unicode(uuid4())
        api = cls(
            root_path=FilePath(root_path),
            compute_instance_id=compute_instance_id,
            allocation_unit=allocation_unit,
        )
        api._initialise_directories()
        return api

    def _initialise_directories(self):
        """
        Create the root and sub-directories in which loopback files will be
        created.
        """
        self._unattached_directory = self._root_path.child(
            self._unattached_directory_name)

        try:
            self._unattached_directory.makedirs()
        except OSError:
            pass

        self._attached_directory = self._root_path.child(
            self._attached_directory_name)

        try:
            self._attached_directory.makedirs()
        except OSError:
            pass

    def allocation_unit(self):
        return self._allocation_unit

    def compute_instance_id(self):
        if not self._compute_instance_id:
            raise UnknownInstanceID(self)
        return self._compute_instance_id

    def _parse_backing_file_name(self, filename):
        """
        :param unicode filename: The backing file name to decode.
        :returns: A 2-tuple of ``unicode`` blockdevice_id, and ``int``
            size.
        """
        blockdevice_id, size = filename.rsplit('_', 1)
        size = int(size)
        return blockdevice_id, size

    def create_volume(self, dataset_id, size):
        """
        Create a "sparse" file of some size and put it in the ``unattached``
        directory.

        See ``IBlockDeviceAPI.create_volume`` for parameter and return type
        documentation.
        """
        check_allocatable_size(self.allocation_unit(), size)
        volume = _blockdevicevolume_from_dataset_id(
            size=size, dataset_id=dataset_id,
        )
        with self._unattached_directory.child(
            _backing_file_name(volume)
        ).open('wb') as f:
            f.truncate(size)
        return volume

    def destroy_volume(self, blockdevice_id):
        """
        Destroy the storage for the given unattached volume.
        """
        volume = get_blockdevice_volume(self, blockdevice_id)
        volume_path = self._unattached_directory.child(
            _backing_file_name(volume)
        )
        volume_path.remove()

    def _allocate_device(self, backing_file_path):
        """
        Create a loopback device backed by the file at the given path.

        :param FilePath backing_file_path: The path of the file that is the
            backing store for the new device.
        """
        # The --find option allocates the next available /dev/loopX device
        # name to the device.
        check_output(["losetup", "--find", backing_file_path.path])

    def attach_volume(self, blockdevice_id, attach_to):
        """
        Move an existing ``unattached`` file into a per-node directory and
        create a loopback device backed by that file.

        Note: Although `mkfs` can format files directly and `mount` can mount
        files directly (with the `-o loop` option), we want to simulate a real
        block device which will be allocated a real block device file on the
        node to which it is attached. This allows the consumer of this API to
        perform formatting and mount operations exactly the same as for a real
        block device.

        See ``IBlockDeviceAPI.attach_volume`` for parameter and return type
        documentation.
        """
        volume = get_blockdevice_volume(self, blockdevice_id)
        filename = _backing_file_name(volume)
        if volume.attached_to is None:
            old_path = self._unattached_directory.child(filename)
            host_directory = self._attached_directory.child(
                attach_to.encode("ascii"),
            )
            try:
                host_directory.makedirs()
            except OSError:
                pass
            new_path = host_directory.child(filename)
            old_path.moveTo(new_path)
            self._allocate_device(new_path)
            attached_volume = volume.set(attached_to=attach_to)
            return attached_volume

        raise AlreadyAttachedVolume(blockdevice_id)

    def detach_volume(self, blockdevice_id):
        """
        Move an existing file from a per-host directory into the ``unattached``
        directory and release the loopback device backed by that file.
        """
        volume = get_blockdevice_volume(self, blockdevice_id)
        if volume.attached_to is None:
            raise UnattachedVolume(blockdevice_id)

        # ``losetup --detach`` only if the file was used for a loop device.
        if self.get_device_path(blockdevice_id) is not None:
            check_output([
                b"losetup", b"--detach",
                self.get_device_path(blockdevice_id).path
            ])

        filename = _backing_file_name(volume)
        volume_path = self._attached_directory.descendant([
            volume.attached_to.encode("ascii"),
            filename,
        ])
        new_path = self._unattached_directory.child(
            filename
        )
        volume_path.moveTo(new_path)

    def list_volumes(self):
        """
        Return ``BlockDeviceVolume`` instances for all the files in the
        ``unattached`` directory and all per-host directories.

        See ``IBlockDeviceAPI.list_volumes`` for parameter and return type
        documentation.
        """
        volumes = []
        for child in self._root_path.child('unattached').children():
            blockdevice_id, size = self._parse_backing_file_name(
                child.basename().decode('ascii')
            )
            volume = _blockdevicevolume_from_blockdevice_id(
                blockdevice_id=blockdevice_id,
                size=size,
            )
            volumes.append(volume)

        for host_directory in self._root_path.child('attached').children():
            compute_instance_id = host_directory.basename().decode('ascii')
            for child in host_directory.children():
                blockdevice_id, size = self._parse_backing_file_name(
                    child.basename().decode('ascii')
                )
                volume = _blockdevicevolume_from_blockdevice_id(
                    blockdevice_id=blockdevice_id,
                    size=size,
                    attached_to=compute_instance_id,
                )
                volumes.append(volume)

        return volumes

    def get_device_path(self, blockdevice_id):
        volume = get_blockdevice_volume(self, blockdevice_id)
        if volume.attached_to is None:
            raise UnattachedVolume(blockdevice_id)

        volume_path = self._attached_directory.descendant(
            [volume.attached_to.encode("ascii"),
             _backing_file_name(volume)]
        )
        # May be None if the file hasn't been used for a loop device.
        path = _device_for_path(volume_path)
        if path is None:
            # It was supposed to be attached (the backing file was stored in a
            # child of the "attached" directory, so someone had called
            # `attach_volume` and not `detach_volume` for it) but it has no
            # loopback device.  So its actual state is only partially attached.
            # Fix it so it's all-the-way attached.  This might happen because
            # the node OS was rebooted, for example.
            self._allocate_device(volume_path)
            path = _device_for_path(volume_path)
        return path
