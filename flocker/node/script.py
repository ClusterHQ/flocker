# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script -*-

"""
The command-line ``flocker-changestate`` tool.
"""

from twisted.python.usage import Options, UsageError
from twisted.internet.defer import succeed

from yaml import safe_load
from yaml.error import YAMLError

from zope.interface import implementer

from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, ICommandLineScript)
from ..node import ConfigurationError, model_from_configuration
from ._deploy import Deployer

__all__ = [
    "ChangeStateOptions",
    "ChangeStateScript",
    "flocker_changestate_main",
]


@flocker_standard_options
class ChangeStateOptions(Options):
    """
    Command line options for ``flocker-changestate`` management tool.
    """

    longdesc = """\
    flocker-changestate is called by flocker-deploy to set the configuration of
    a node.

    * deployment_configuration: The YAML string describing the desired
        deployment configuration.

    * application_configuration: The YAML string describing the desired
        application configuration.

    * hostname: The hostname of this node. Used by the node to identify which
        applications from deployment_configuration should be running.
    """
    synopsis = ("Usage: flocker-changestate [OPTIONS] "
                "<deployment configuration> <application configuration> "
                "<hostname>")

    def parseArgs(self, deployment_config, application_config, hostname):
        """
        Parse `deployment_config` and `application_config` strings as YAML, and
        into a :class:`Deployment` instance. Assign the resulting instance
        to this `Options` dictionary.

        :param bytes deployment_config: The YAML string describing the desired
            deployment configuration.
        :param bytes application_config: The YAML string describing the desired
            application configuration.
        :param bytes hostname: The ascii encoded hostname of this node.

        :raises UsageError: If the configuration files cannot be parsed as YAML
            and into a :class:`Deployment` instance.
        """
        try:
            deployment_config = safe_load(deployment_config)
        except YAMLError as e:
            raise UsageError(
                "Deployment config could not be parsed as YAML:\n\n" + str(e)
            )
        try:
            application_config = safe_load(application_config)
        except YAMLError as e:
            raise UsageError(
                "Application config could not be parsed as YAML:\n\n" + str(e)
            )
        try:
            self['hostname'] = hostname.decode('ascii')
        except UnicodeDecodeError:
            raise UsageError(
                "Non-ASCII hostname: {hostname}".format(hostname=hostname)
            )

        try:
            self['deployment'] = model_from_configuration(
                application_configuration=application_config,
                deployment_configuration=deployment_config)
        except ConfigurationError as e:
            raise UsageError(
                'Configuration Error: {error}'
                .format(error=str(e))
            )


@implementer(ICommandLineScript)
class ChangeStateScript(object):
    """
    A command to get a node into a desired state by pushing volumes, starting
    and stopping applications, opening up application ports and setting up
    routes to other nodes.

    :ivar Deployer _deployer: A :class:`Deployer` instance used to change the
        state of the current node.
    """
    _deployer = Deployer()

    def main(self, reactor, options):
        """
        See :py:meth:`ICommandLineScript.main` for parameter documentation.
        """
        return succeed(None)


def flocker_changestate_main():
    return FlockerScriptRunner(
        script=ChangeStateScript(),
        options=ChangeStateOptions()
    ).main()
