# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-changestate`` tool."""
# TODO change it all to flocker-changestate

from twisted.python.usage import Options, UsageError
from twisted.internet.defer import succeed

from yaml import safe_load
from yaml.error import YAMLError

from zope.interface import implementer

from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, ICommandLineScript)

__all__ = [
    "ChangeStateOptions",
    "ChangeStateScript",
    "flocker_node_main",
]


@flocker_standard_options
class ChangeStateOptions(Options):
    """Command line options for ``flocker-changestate`` node management tool."""

    longdesc = """flocker-changestate allows you to set configs.

    """
    synopsis = ("Usage: flocker-changestate [OPTIONS] "
                "DEPLOYMENT_CONFIGURATION APPLICATION_CONFIGURATION")

    def parseArgs(self, deployment_config, app_config):
        # TODO store these as config objects
        try:
            self['deployment_config'] = safe_load(deployment_config)
        except YAMLError as e:
            raise UsageError("Deployment config could not be parsed as YAML:\n\n"+str(e))
        try:
            self['app_config'] = safe_load(app_config)
        except YAMLError as e:
	    raise UsageError("Application config could not be parsed as YAML:\n\n"+str(e))

@implementer(ICommandLineScript)
class ChangeStateScript(object):
    """
    TODO
    """
    def main(self, reactor, options):
        """
        TODO

        See :py:meth:`ICommandLineScript.main` for parameter documentation.
        """
        return succeed(None)


def flocker_changestate_main():
    return FlockerScriptRunner(
        script=ChangeStateScript(),
        options=ChangeStateOptions()
    ).main()
