# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-node`` tool."""
# TODO change it all to flocker-changestate

from twisted.python.usage import Options, UsageError
from twisted.internet.defer import succeed

from yaml import safe_load
from yaml.error import YAMLError

from zope.interface import implementer

from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, ICommandLineScript)

__all__ = [
    # TODO
]


@flocker_standard_options
class NodeOptions(Options):
    """Command line options for ``flocker-node`` node management tool."""

    longdesc = """flocker-node allows you to set configs.

    """
    synopsis = ("Usage: flocker-node [OPTIONS] "
                "DEPLOYMENT_CONFIGURATION APPLICATION_CONFIGURATION")

    def parseArgs(self, deployment_config, app_config):
        # TODO store these as config objects
        try:
            self['deployment_config'] = safe_load(deployment_config)
        except YAMLError:
            raise UsageError("Deployment config could not be parsed as YAML")
        try:
            self['app_config'] = safe_load(app_config)
        except YAMLError:
	    raise UsageError("Application config could not be parsed as YAML")

@implementer(ICommandLineScript)
class NodeScript(object):
    """
    TODO
    """
    def main(self, reactor, options):
        """
        TODO

        See :py:meth:`ICommandLineScript.main` for parameter documentation.
        """
        return succeed(None)


def flocker_node_main():
    return FlockerScriptRunner(
        script=NodeScript(),
        options=NodeOptions()
    ).main()
