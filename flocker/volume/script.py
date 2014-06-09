# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-volume`` tool."""

import sys

from twisted.python.usage import Options
from twisted.python.filepath import FilePath
from twisted.internet.task import react
from twisted.internet.defer import succeed

from .service import VolumeService, CreateConfigurationError
from .. import __version__


class FlockerVolumeOptions(Options):
    """Command line options for ``flocker-volume`` volume management tool."""

    longdesc = """flocker-volume allows you to manage volumes, filesystems
    that can be attached to Docker containers.

    At the moment no functionality has been implemented.
    """

    optParameters = [
        ["config", None, b"/etc/flocker/volume.json",
         "The path to the config file."],
    ]

    def postOptions(self):
        self["config"] = FilePath(self["config"])

    def opt_version(self):
        """Print the program's version and exit."""
        print(__version__)
        raise SystemExit(0)


def _main(reactor, *arguments):
    """Parse command-line options and use them to run volume management."""
    # Much of this should be moved (and expanded) into shared class:
    # https://github.com/hybridlogic/flocker/issues/30
    options = FlockerVolumeOptions()
    options.parseOptions(arguments)
    service = VolumeService(options["config"], None)
    try:
        service.startService()
    except CreateConfigurationError as e:
        sys.stderr.write(b"Writing config file %s failed: %s\n" % (
            options["config"].path, e))
        raise SystemExit(1)
    return succeed(None)


def main():
    """Entry point to the ``flocker-volume`` command-line tool."""
    react(_main, sys.argv[1:])
