# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-volume`` tool."""

import sys

from twisted.python.usage import Options
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed

from zope.interface import implementer

from .service import (
    VolumeService, CreateConfigurationError, DEFAULT_CONFIG_PATH,
    )
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, ICommandLineScript)


__all__ = [
    'flocker_volume_main',
    'VolumeOptions',
    'VolumeScript',
]

class ReceiveSubcommandOptions(Options):
    """Command line options ``flocker-volume receive``."""

    longdesc = """Receive a volume pushed from another volume manager.

    Reads the volume in from standard in. This is typically called
    automatically over SSH.
    """

    def parseArgs(self, uuid, name):
        self["uuid"] = uuid.decode("ascii")
        self["name"] = name.decode("ascii")


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
    ]

    subCommands = [
        ["receive", None, ReceiveSubcommandOptions,
         "Receive a remotely pushed volume."],
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
        service = self._service_factory(
            config_path=options["config"], pool=None)
        try:
            service.startService()
        except CreateConfigurationError as e:
            self._sys_module.stderr.write(
                b"Writing config file %s failed: %s\n" % (
                    options["config"].path, e)
            )
            raise SystemExit(1)

        if options.subCommand == "receive":
            service.receive(options.subOptions["uuid"],
                            options.subOptions["name"],
                            sys.stdin)
        return succeed(None)


def flocker_volume_main():
    return FlockerScriptRunner(
        script=VolumeScript(),
        options=VolumeOptions()
    ).main()
