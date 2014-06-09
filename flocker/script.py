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
def flocker(self):
    click.echo()



@click.command()
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
