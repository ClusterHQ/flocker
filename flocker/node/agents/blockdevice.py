# -*- test-case-name: flocker.node.agents.test.test_blockdevice -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
This module implements the parts of a block-device based dataset
convergence agent that can be re-used against many different kinds of block
devices.
"""

from uuid import uuid4
from subprocess import check_output

from zope.interface import implementer, Interface

from characteristic import attributes
from pyrsistent import PRecord, field

from twisted.python.filepath import FilePath


class VolumeException(Exception):
    """
    A base class for exceptions raised by  ``IBlockDeviceAPI`` operations.

    :param unicode blockdevice_id: The unique identifier of the block device.
    """
    def __init__(self, blockdevice_id):
        if not isinstance(blockdevice_id, unicode):
            raise TypeError(
                'Unexpected blockdevice_id type. '
                'Expected unicode. '
                'Got {!r}.'.format(blockdevice_id)
            )
        Exception.__init__(self, blockdevice_id)
        self.blockdevice_id = blockdevice_id


class UnknownVolume(VolumeException):
    """
    The block device could not be found.
    """


class AlreadyAttachedVolume(VolumeException):
    """
    A failed attempt to attach a block device that is already attached.
    """


class UnattachedVolume(VolumeException):
    """
    An attempt was made to operate on an unattached volume but the operation
    requires the volume to be attached.
    """


# TODO: Introduce a non-blocking version of this interface and an automatic
# thread-based wrapper for adapting this to the other.  Use that interface
# anywhere being non-blocking is important (which is probably lots of places).
# See https://clusterhq.atlassian.net/browse/FLOC-1549
class IBlockDeviceAPI(Interface):
    """
    Common operations provided by all block device backends.

    Note: This is an early sketch of the interface and it'll be refined as we
    real blockdevice providers are implemented.
    """
    def create_volume(size):
        """
        Create a new block device.

        XXX: Probably needs to be some checking of valid sizes for different
        backends. Perhaps the allowed sizes should be defined as constants?

        :param int size: The size of the new block device in bytes.
        :returns: A ``BlockDeviceVolume``.
        """

    def attach_volume(blockdevice_id, host):
        """
        Attach ``blockdevice_id`` to ``host``.

        :param unicode blockdevice_id: The unique identifier for the block
            device being attached.
        :param bytes host: The IP address of a host to attach the volume to.
        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.
        :raises AlreadyAttachedVolume: If the supplied ``blockdevice_id`` is
            already attached.
        :returns: A ``BlockDeviceVolume`` with a ``host`` attribute set to
            ``host``.
        """

    def list_volumes():
        """
        List all the block devices available via the back end API.

        :returns: A ``list`` of ``BlockDeviceVolume``s.
        """

    def get_device_path(blockdevice_id):
        """
        Calculate the path at which ``blockdevice_id`` will be exposed on the
        host when attached.

        :param unicode blockdevice_id: The unique identifier for the block
            device.
        :returns: A ``FilePath`` for the device.
        """


class BlockDeviceVolume(PRecord):
    """
    A block device that may be attached to a host.

    :ivar unicode blockdevice_id: The unique identifier of the block device.
    :ivar int size: The size of the block device.
    :ivar bytes host: The IP address of the host to which the block device is
        attached or ``None`` if it is currently unattached.
    """
    blockdevice_id = field(type=unicode, mandatory=True)
    size = field(type=int, mandatory=True)
    # XXX: Should be hostname, for consistency of is host a better name since
    # we currently only expect IP addresses?
    host = field(type=(bytes, type(None)), initial=None)


def losetup_list_parse(output):
    """
    Parse the output of ``losetup --all`` which varies depending on the
    privileges of the user.

    :param unicode output: The output of ``losetup --all``.
    :returns: A ``list`` of
        2-tuple(FilePath(device_file), FilePath(backing_file))
    """
    devices = []
    for line in output.splitlines():
        parts = line.split(':', 2)
        if len(parts) != 3:
            continue
        device_file, attributes, backing_file = parts
        device_file = FilePath(device_file.strip())

        # Trim everything from the first left bracket, skipping over the
        # possible inode number which appears only when run as root.
        left_bracket_offset = backing_file.find('(')
        backing_file = backing_file[left_bracket_offset+1:]

        # Trim everything from the right most right bracket
        right_bracket_offset = backing_file.rfind(')')
        backing_file = backing_file[:right_bracket_offset]

        # Trim a possible embedded deleted flag
        expected_suffix_list = ['(deleted)']
        for suffix in expected_suffix_list:
            offset = backing_file.rfind(suffix)
            if offset > -1:
                backing_file = backing_file[:offset]

        # Remove the space that may have been between the path and the deleted
        # flag.
        backing_file = backing_file.rstrip()
        backing_file = FilePath(backing_file)
        devices.append((device_file, backing_file))
    return devices


def losetup_list():
    """
    List all the loopback devices on the system.

    :returns: A ``list`` of
        2-tuple(FilePath(device_file), FilePath(backing_file))
    """
    output = check_output(
        ["losetup", "--all"]
    ).decode('utf8')
    return losetup_list_parse(output)


def device_for_path(expected_backing_file):
    """
    :param FilePath backing_file: A path which may be associated with a
        loopback device.
    :returns: A ``FilePath`` to the loopback device if one is found, or
        ``None`` if no device exists.
    """
    for device_file, backing_file in losetup_list():
        if expected_backing_file == backing_file:
            return device_file
    return None


@implementer(IBlockDeviceAPI)
@attributes(['root_path'])
class LoopbackBlockDeviceAPI(object):
    """
    A simulated ``IBlockDeviceAPI`` which creates loopback devices backed by
    files located beneath the supplied ``root_path``.
    """
    _attached_directory_name = 'attached'
    _unattached_directory_name = 'unattached'

    @classmethod
    def from_path(cls, root_path):
        """
        :param bytes root_path: The path to a directory in which loop back
            backing files will be created. The directory is created if it does
            not already exist.
        :returns: A ``LoopbackBlockDeviceAPI`` with the supplied ``root_path``.
        """
        api = cls(root_path=FilePath(root_path))
        api._initialise_directories()
        return api

    def _initialise_directories(self):
        """
        Create the root and sub-directories in which loopback files will be
        created.
        """
        self._unattached_directory = self.root_path.child(
            self._unattached_directory_name)

        try:
            self._unattached_directory.makedirs()
        except OSError:
            pass

        self._attached_directory = self.root_path.child(
            self._attached_directory_name)

        try:
            self._attached_directory.makedirs()
        except OSError:
            pass

    def create_volume(self, size):
        """
        Create a file of some size and put it in the ``unattached`` directory.

        See ``IBlockDeviceAPI.create_volume`` for parameter and return type
        documentation.
        """
        volume = BlockDeviceVolume(
            blockdevice_id=unicode(uuid4()),
            size=size,
        )
        self._unattached_directory.child(
            volume.blockdevice_id.encode('ascii')
        ).setContent(b'\0' * volume.size)
        return volume

    def _get(self, blockdevice_id):
        for volume in self.list_volumes():
            if volume.blockdevice_id == blockdevice_id:
                return volume
        raise UnknownVolume(blockdevice_id)

    def attach_volume(self, blockdevice_id, host):
        """
        Move an existing ``unattached`` file into a per-host directory.

        See ``IBlockDeviceAPI.attach_volume`` for parameter and return type
        documentation.
        """
        volume = self._get(blockdevice_id)
        if volume.host is None:
            old_path = self._unattached_directory.child(blockdevice_id)
            host_directory = self._attached_directory.child(host)
            try:
                host_directory.makedirs()
            except OSError:
                pass
            new_path = host_directory.child(blockdevice_id)
            old_path.moveTo(new_path)
            check_output(["losetup", "--find", new_path.path])
            attached_volume = volume.set(host=host)
            return attached_volume

        raise AlreadyAttachedVolume(blockdevice_id)

    def list_volumes(self):
        """
        Return ``BlockDeviceVolume`` instances for all the files in the
        ``unattached`` directory and all per-host directories.

        See ``IBlockDeviceAPI.list_volumes`` for parameter and return type
        documentation.
        """
        volumes = []
        for child in self.root_path.child('unattached').children():
            volume = BlockDeviceVolume(
                blockdevice_id=child.basename().decode('ascii'),
                size=child.getsize(),
            )
            volumes.append(volume)

        for host_directory in self.root_path.child('attached').children():
            host_name = host_directory.basename().encode('ascii')
            for child in host_directory.children():

                volume = BlockDeviceVolume(
                    blockdevice_id=child.basename().decode('ascii'),
                    size=child.getsize(),
                    host=host_name,
                )
                volumes.append(volume)

        return volumes

    def get_device_path(self, blockdevice_id):
        volume = self._get(blockdevice_id)
        if volume.host is None:
            raise UnattachedVolume(blockdevice_id)

        volume_path = self._attached_directory.descendant(
            [volume.host, volume.blockdevice_id]
        )
        # May be None if the file hasn't been used for a loop device.
        return device_for_path(volume_path)
