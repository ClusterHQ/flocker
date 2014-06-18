# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-volume`` tool."""
import sys

from twisted.python.usage import Options
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed

from .service import VolumeService, CreateConfigurationError
from flocker.common.script import flocker_standard_options, FlockerScriptRunner


@flocker_standard_options
class VolumeOptions(Options):
    """Command line options for ``flocker-volume`` volume management tool."""

    longdesc = """flocker-volume allows you to manage volumes, filesystems
    that can be attached to Docker containers.

    At the moment no functionality has been implemented.
    """
    synopsis = "Usage: flocker-volume [OPTIONS]"

    optParameters = [
        ["config", None, b"/etc/flocker/volume.json",
         "The path to the config file."],
    ]

    def postOptions(self):
        self["config"] = FilePath(self["config"])


class VolumeScript(object):
    """
    A volume manager script.
    """
    _service_factory = VolumeService

    def __init__(self, sys_module=None):
        """
        """
        if sys_module is None:
            sys_module = sys
        self._sys_module = sys_module

    def main(self, reactor, options):
        """
        Run a volume management server configured according to the supplied
        options.
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
        return succeed(None)


flocker_volume_main = FlockerScriptRunner(
    script=VolumeScript(),
    options=VolumeOptions()
).main


__all__ = [
    'flocker_volume_main',
    'VolumeOptions',
    'VolumeScript',
]
