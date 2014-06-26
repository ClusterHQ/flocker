from twisted.python.usage import Options

from zope.interface import implementer
from ..common.script import flocker_standard_options, ICommandLineScript

@flocker_standard_options
class DeployOptions(Options):
    """
    Command line options for ``flocker-deploy``.
    """
    synopsis = "Usage: flocker-deploy"


@implementer(ICommandLineScript)
class DeployScript(object):
    """
    A script to start configured deployments, covered by:
       https://github.com/hybridlogic/flocker/issues/19
    """
    def main(self, reactor, options):
        return True
