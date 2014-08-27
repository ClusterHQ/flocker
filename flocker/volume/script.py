# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-volume`` tool."""

import sys

from twisted.python.usage import Options
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed, maybeDeferred

from zope.interface import implementer

from .service import (
    DEFAULT_CONFIG_PATH, FLOCKER_MOUNTPOINT, FLOCKER_POOL,
    VolumeScript, ICommandLineVolumeScript
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
         "containing the UUID of the Flocker volume service on this node. "
         "This file will be created if it does not already exist."],
        # Maybe we can come up with something better in
        # https://github.com/ClusterHQ/flocker/issues/125
        ["pool", None, FLOCKER_POOL,
         "The ZFS pool to use for volumes."],
        ["mountpoint", None, FLOCKER_MOUNTPOINT.path,
         "The path where ZFS filesystems will be mounted."],
    ]

    original_postOptions = cls.postOptions

    def postOptions(self):
        self["config"] = FilePath(self["config"])
        self["mountpoint"] = FilePath(self["mountpoint"])
        original_postOptions(self)

    cls.postOptions = postOptions

    return cls


class _ReceiveSubcommandOptions(Options):
    """Command line options for ``flocker-volume receive``."""

    longdesc = """Receive a volume pushed from another volume manager.

    Reads the volume in from standard in. This is typically called
    automatically over SSH.

    Parameters:

    * owner-uuid: The UUID of the volume manager that owns the volume.

    * name: The name of the volume.
    """

    synopsis = "<owner-uuid> <name>"

    def parseArgs(self, uuid, name):
        self["uuid"] = uuid.decode("ascii")
        self["name"] = name.decode("ascii")

    def run(self, service):
        """Run the action for this sub-command.

        :param VolumeService service: The volume manager service to utilize.
        """
        service.receive(self["uuid"], self["name"], sys.stdin)


class _AcquireSubcommandOptions(Options):
    """
    Command line options for ``flocker-volume acquire``.
    """

    longdesc = """\
    Take ownership of a volume previously owned by another volume manager.

    Reads the volume in from standard in. This is typically called
    automatically over SSH.

    Parameters:

    * owner-uuid: The UUID of the volume manager that owns the volume.

    * name: The name of the volume.
    """

    synopsis = "<owner-uuid> <name>"

    def parseArgs(self, uuid, name):
        self["uuid"] = uuid.decode("ascii")
        self["name"] = name.decode("ascii")

    def run(self, service):
        """
        Run the action for this sub-command.

        :param VolumeService service: The volume manager service to utilize.
        """
        d = service.acquire(self["uuid"], self["name"])

        def acquired(_):
            sys.stdout.write(service.uuid.encode("ascii"))
            sys.stdout.flush()
        d.addCallback(acquired)
        return d


@flocker_standard_options
@flocker_volume_options
class VolumeOptions(Options):
    """Command line options for ``flocker-volume`` volume management tool."""

    longdesc = """flocker-volume allows you to manage volumes, filesystems
    that can be attached to Docker containers.

    """
    synopsis = "Usage: flocker-volume [OPTIONS]"

    subCommands = [
        ["receive", None, _ReceiveSubcommandOptions,
         "Receive a remotely pushed volume."],
        ["acquire", None, _AcquireSubcommandOptions,
         "Acquire a remotely owned volume."],
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
        options=VolumeOptions()
    ).main()
