# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A top level flocker command.
"""
from . import __version__


from twisted.python.usage import Options
from twisted.python.filepath import FilePath


def flocker_standard_options(cls):
    def opt_version(self):
        """
        Print the program's version and exit.
        """
        print(__version__)
        raise SystemExit(0)
    cls.opt_version = opt_version
    cls.opt_v = opt_version

    return cls



@flocker_standard_options
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
