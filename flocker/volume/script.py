"""The command-line ``flocker-volume`` tool."""

from twisted.python.usage import Options
from twisted.python.filepath import FilePath


class FlockerVolumeOptions(Options):
    """flocker-volume - volume management."""

    optParameters = [
        ["config", None, b"/etc/flocker/volume.json",
         "The path to the config file."],
    ]

    def postOptions(self):
        self["config"] = FilePath(self["config"])
