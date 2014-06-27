# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-deploy`` tool."""
from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from twisted.python.usage import Options

from zope.interface import implementer
from ..common.script import (flocker_standard_options, ICommandLineScript,
                             FlockerScriptRunner)


@flocker_standard_options
class DeployOptions(Options):
    """
    Command line options for ``flocker-deploy``.
    """
    synopsis = ("Usage: flocker-deploy [OPTIONS] ",
                "DEPLOYMENT_CONFIGURATION_PATH APPLICATION_CONFIGURATION_PATH")

    def parseArgs(self, deployment_config, app_config):
        deployment_config = FilePath(deployment_config)
        app_config = FilePath(app_config)

        if not deployment_config.exists():
            raise ValueError

        if not app_config.exists():
            raise ValueError

        self['deployment_config'] = deployment_config
        self['app_config'] = app_config


@implementer(ICommandLineScript)
class DeployScript(object):
    """
    A script to start configured deployments, covered by:
       https://github.com/hybridlogic/flocker/issues/19
    """
    def main(self, reactor, options):
        """
        Returns a ``Deferred``. This is a stub.

        :return: A ``Deferred`` which fires with ``None``.
        """
        return succeed(None)


def flocker_deploy_main():
    return FlockerScriptRunner(
        script=DeployScript(),
        options=DeployOptions()
    ).main()
