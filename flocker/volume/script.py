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
    'VolumeOptions',
    'VolumeManagerScript',
]


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
class VolumeOptions(Options):
    """Command line options for ``flocker-volume`` volume management tool."""

    longdesc = """flocker-volume allows you to manage volumes, filesystems
    that can be attached to Docker containers.

    """
    synopsis = "Usage: flocker-volume [OPTIONS]"

    optParameters = [
        ["config", None, DEFAULT_CONFIG_PATH.path,
         "The path to the config file."],
        # Maybe we can come up with something better in
        # https://github.com/ClusterHQ/flocker/issues/125
        ["pool", None, FLOCKER_POOL,
         "The ZFS pool to use for volumes."],
        ["mountpoint", None, FLOCKER_MOUNTPOINT.path,
         "The path where ZFS filesystems will be mounted."],
    ]

    subCommands = [
        ["receive", None, _ReceiveSubcommandOptions,
         "Receive a remotely pushed volume."],
        ["acquire", None, _AcquireSubcommandOptions,
         "Acquire a remotely owned volume."],
    ]

    def postOptions(self):
        self["config"] = FilePath(self["config"])


@implementer(ICommandLineVolumeScript)
class VolumeManagerScript(object):
    """
    A volume manager script.
    """
    def main(self, reactor, options):
        """
        Run a volume management operation.

        The volume manager will be configured according to the supplied
        options.

        See :py:meth:`ICommandLineVolumeScript.main` for parameter
            documentation.
        """
        service = self.create_volume_service(reactor, options)
        if options.subCommand is not None:
            return maybeDeferred(options.subOptions.run, service)
        else:
            return succeed(None)


def flocker_volume_main():
    return FlockerScriptRunner(
        script=VolumeScript(VolumeManagerScript()),
        options=VolumeOptions()
    ).main()
