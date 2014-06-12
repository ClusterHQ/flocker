# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A top level flocker command.
"""

import click

from twisted.python import filepath

from . import __version__


class FilePath(click.ParamType):
    """
    A wrapper around L{click.Path} which returns a
    L{twisted.python.filepath.FilePath}.
    """
    name = 'filepath'

    def __init__(self, *args, **kwargs):
        self.path = click.Path(*args, **kwargs)


    def convert(self, value, param, ctx):
        value = self.path.convert(value, param, ctx)
        return filepath.FilePath(value)



@click.group()
@click.help_option()
@click.version_option(version=__version__)
def flocker():
    pass



@flocker.command()
@click.help_option()
@click.option(
    '--config',
    type=FilePath(),
    default=b"/etc/flocker/volume.json",
    help='The path to the config file.'
)
def volume(config):
    """
    """
    click.echo()



from twisted.python.usage import Options
from twisted.python.filepath import FilePath
from . import __version__

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
