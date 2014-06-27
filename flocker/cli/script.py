# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-deploy`` tool."""
from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from twisted.python.usage import Options

from zope.interface import implementer
from ..common.script import flocker_standard_options, ICommandLineScript


@flocker_standard_options
class DeployOptions(Options):
    """
    Command line options for ``flocker-deploy``.
    """
    synopsis = "Usage: flocker-deploy"

    def parseArgs(self, deploy, app):
        deploy = FilePath(deploy)
        deploy = FilePath(app)

        self['deploy'] = deploy
        self['app'] = app


@implementer(ICommandLineScript)
class DeployScript(object):
    """
    A script to start configured deployments, covered by:
       https://github.com/hybridlogic/flocker/issues/19
    """
    def main(self, reactor, options):
        return succeed(None)
