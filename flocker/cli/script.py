# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-deploy`` tool."""
from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from zope.interface import implementer

from yaml import safe_load

from ..common.script import (flocker_standard_options, ICommandLineScript,
                             FlockerScriptRunner)
from ..node import ConfigurationError, model_from_configuration
from ._sshconfig import OpenSSHConfiguration


@flocker_standard_options
class DeployOptions(Options):
    """
    Command line options for ``flocker-deploy``.

    :raises ValueError: If either file supplied does not exist.
    """
    longdesc = """flocker-deploy allows you to configure existing nodes.

    """

    synopsis = ("Usage: flocker-deploy [OPTIONS] "
                "DEPLOYMENT_CONFIGURATION_PATH APPLICATION_CONFIGURATION_PATH")

    def parseArgs(self, deployment_config, application_config):
        deployment_config = FilePath(deployment_config)
        application_config = FilePath(application_config)

        if not deployment_config.exists():
            raise UsageError('No file exists at {path}'
                             .format(path=deployment_config.path))

        if not application_config.exists():
            raise UsageError('No file exists at {path}'
                             .format(path=application_config.path))

        deployment_config = safe_load(deployment_config.getContent())
        application_config = safe_load(application_config.getContent())
        try:
            self['deployment'] = model_from_configuration(
                deployment_config, application_config)
        except ConfigurationError as e:
            raise UsageError(str(e))


@implementer(ICommandLineScript)
class DeployScript(object):
    """
    A script to start configured deployments, covered by:
       https://github.com/ClusterHQ/flocker/issues/19
    """
    def __init__(self, ssh_configuration=None, ssh_port=22):
        if ssh_configuration is None:
	    ssh_configuration = OpenSSHConfiguration.defaults()
	self.ssh_configuration = ssh_configuration
	self.ssh_port = ssh_port

    def main(self, reactor, options):
        """
        Returns a ``Deferred``. This is a stub.

        :return: A ``Deferred`` which fires with ``None``.
        """
        deployment = options["deployment"]
	for node in deployment.nodes:
	    self.ssh_configuration.configure_ssh(node.hostname, self.ssh_port)
	print deployment
        return succeed(None)


def flocker_deploy_main():
    return FlockerScriptRunner(
        script=DeployScript(),
        options=DeployOptions()
    ).main()
