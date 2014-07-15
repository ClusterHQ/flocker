# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-volume`` tool."""

import sys

from twisted.python.usage import Options
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed, maybeDeferred

from zope.interface import implementer

from .service import (
    VolumeService, CreateConfigurationError, DEFAULT_CONFIG_PATH,
    )
from .filesystems.zfs import StoragePool
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, ICommandLineScript)


__all__ = [
    'flocker_volume_main',
    'VolumeOptions',
    'VolumeScript',
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
        ["pool", None, b"flocker",
         "The ZFS pool to use for volumes."],
        ["mountpoint", None, b"/flocker",
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


@implementer(ICommandLineScript)
class VolumeScript(object):
    """A volume manager script.

    :ivar IService _service: ``VolumeService`` by default but can be overridden
        for testing purposes.
    """
    _service_factory = VolumeService

    def __init__(self, sys_module=None):
        """
        :param sys_module: An optional ``sys`` like fake module for use in
            testing. Defaults to ``sys``.
        """
        if sys_module is None:
            sys_module = sys
        self._sys_module = sys_module

    def main(self, reactor, options):
        """Run a volume management server

        The server will be configured according to the supplied options.

        See :py:meth:`ICommandLineScript.main` for parameter documentation.
        """
        if options.subCommand is None:
            pool = None
        else:
            pool = StoragePool(reactor, options["pool"],
                               FilePath(options["mountpoint"]))
        service = self._service_factory(
            config_path=options["config"], pool=pool, reactor=reactor)
        try:
            service.startService()
        except CreateConfigurationError as e:
            self._sys_module.stderr.write(
                b"Writing config file %s failed: %s\n" % (
                    options["config"].path, e)
            )
            raise SystemExit(1)

        if options.subCommand is not None:
            return maybeDeferred(options.subOptions.run, service)
        else:
            return succeed(None)


def flocker_volume_main():
    return FlockerScriptRunner(
        script=VolumeScript(),
        options=VolumeOptions()
    ).main()
