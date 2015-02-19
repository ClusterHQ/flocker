# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-volume`` tool."""

import sys

from twisted.python.usage import Options
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed, maybeDeferred

from zope.interface import implementer

from .service import (
    DEFAULT_CONFIG_PATH, FLOCKER_MOUNTPOINT, FLOCKER_POOL,
    Volume, VolumeScript, ICommandLineVolumeScript, VolumeName,
    )
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner
    )


__all__ = [
    'flocker_volume_main',
    'flocker_volume_options',
    'VolumeOptions',
    'VolumeManagerScript',
]


def flocker_volume_options(cls):
    """
    A class decorator to add ``VolumeService`` specific command line options to
    flocker commands.

    :param cls: The class to decorate.
    :return: The decorated class.
    """
    original_parameters = getattr(cls, "optParameters", [])
    cls.optParameters = original_parameters + [
        ["config", None, DEFAULT_CONFIG_PATH.path,
         "The path to the Flocker volume configuration file, "
         "containing the node ID of the Flocker volume service on this node. "
         "This file will be created if it does not already exist."],
        # Maybe we can come up with something better in
        # https://clusterhq.atlassian.net/browse/FLOC-125
        ["pool", None, FLOCKER_POOL,
         "The ZFS pool to use for volumes."],
        ["mountpoint", None, FLOCKER_MOUNTPOINT.path,
         "The path where ZFS filesystems will be mounted."],
    ]

    original_postOptions = cls.postOptions

    def postOptions(self):
        self["config"] = FilePath(self["config"])
        original_postOptions(self)

    cls.postOptions = postOptions

    return cls


class _SnapshotsSubcommandOptions(Options):
    """
    Command line options for ``flocker-volume snapshots``.
    """

    longdesc = """List local snapshots of a particular volume.

    Parameters:

    * owner-node-id: The node ID of the volume manager that owns the volume.

    * name: The name of the volume.
    """

    def parseArgs(self, node_id, name):
        self["node_id"] = node_id.decode("ascii")
        self["name"] = name

    def run(self, service):
        volume = Volume(node_id=self["node_id"],
                        name=VolumeName.from_bytes(self["name"]),
                        service=service)
        filesystem = volume.get_filesystem()
        snapshots = filesystem.snapshots()

        def got_snapshots(snapshots):
            for snapshot in snapshots:
                sys.stdout.write(snapshot.name + b"\n")

        snapshots.addCallback(got_snapshots)
        return snapshots


class _ReceiveSubcommandOptions(Options):
    """Command line options for ``flocker-volume receive``."""

    longdesc = """Receive a volume pushed from another volume manager.

    Reads the volume in from standard in. This is typically called
    automatically over SSH.

    Parameters:

    * owner-node-id: The node ID of the volume manager that owns the volume.

    * name: The name of the volume.
    """

    synopsis = "<owner-node-id> <name>"

    def parseArgs(self, node_id, name):
        self["node_id"] = node_id.decode("ascii")
        self["name"] = name

    def run(self, service):
        """Run the action for this sub-command.

        :param VolumeService service: The volume manager service to utilize.
        """
        service.receive(self["node_id"], VolumeName.from_bytes(self["name"]),
                        sys.stdin)


class _AcquireSubcommandOptions(Options):
    """
    Command line options for ``flocker-volume acquire``.
    """

    longdesc = """\
    Take ownership of a volume previously owned by another volume manager.

    Reads the volume in from standard in. This is typically called
    automatically over SSH.

    Parameters:

    * owner-node-id: The node ID of the volume manager that owns the volume.

    * name: The name of the volume.
    """

    synopsis = "<owner-node-id> <name>"

    def parseArgs(self, node_id, name):
        self["node_id"] = node_id.decode("ascii")
        self["name"] = name

    def run(self, service):
        """
        Run the action for this sub-command.

        :param VolumeService service: The volume manager service to utilize.
        """
        d = service.acquire(self["node_id"],
                            VolumeName.from_bytes(self["name"]))

        def acquired(_):
            sys.stdout.write(service.node_id.encode("ascii"))
            sys.stdout.flush()
        d.addCallback(acquired)
        return d


class _CloneToSubcommandOptions(Options):
    """
    Command line options for ``flocker-volume clone_to``.
    """

    longdesc = """\
    Clone an existing volume, creating a new one.

    Parameters:

    * owner node-id: The node ID of the volume manager that owns the
      parent volume.

    * parent name: The name of the parent volume.

    * child name: The name of the new volume.
    """

    synopsis = "<owner node id> <parent name> <child name>"

    def parseArgs(self, node_id, parent_name, child_name):
        self["node_id"] = node_id.decode("ascii")
        self["parent_name"] = parent_name
        self["child_name"] = child_name

    def run(self, service):
        """
        Run the action for this sub-command.

        :param VolumeService service: The volume manager service to utilize.
        """
        parent = Volume(node_id=self["node_id"],
                        name=VolumeName.from_bytes(self["parent_name"]),
                        service=service)
        return service.clone_to(
            parent, VolumeName.from_bytes(self["child_name"]))


@flocker_standard_options
@flocker_volume_options
class VolumeOptions(Options):
    """Command line options for ``flocker-volume`` volume management tool."""

    longdesc = """flocker-volume allows you to manage volumes, filesystems
    that can be attached to Docker containers.

    """
    synopsis = "Usage: flocker-volume [OPTIONS]"

    subCommands = [
        ["snapshots", None, _SnapshotsSubcommandOptions,
         "List snapshots for a volume."],
        ["receive", None, _ReceiveSubcommandOptions,
         "Receive a remotely pushed volume."],
        ["acquire", None, _AcquireSubcommandOptions,
         "Acquire a remotely owned volume."],
        ["clone_to", None, _CloneToSubcommandOptions,
         "Clone an existing volume."],
    ]


@implementer(ICommandLineVolumeScript)
class VolumeManagerScript(object):
    """
    A volume manager script.
    """
    def main(self, reactor, options, service):
        """
        Run a volume management operation.

        The volume manager will be configured according to the supplied
        options.

        See :py:meth:`ICommandLineVolumeScript.main` for parameter
            documentation.
        """
        if options.subCommand is not None:
            return maybeDeferred(options.subOptions.run, service)
        else:
            return succeed(None)


def flocker_volume_main():
    return FlockerScriptRunner(
        script=VolumeScript(VolumeManagerScript()),
        options=VolumeOptions(),
        logging=False,
    ).main()
