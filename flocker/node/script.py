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
    * hostname: The hostname of this node.
    """
    synopsis = ("Usage: flocker-changestate [OPTIONS] "
                "<deployment_configuration <application_configuration> "
                "<hostname>")

    def parseArgs(self, deployment_config, app_config, hostname):
        """
        Parse `deployment_config` and `app_config` strings as YAML and assign
        the resulting dictionaries to this `Options` dictionary.

        :param bytes deployment_config: The YAML string describing the desired
            deployment configuration.
        :param bytes app_config: The YAML string describing the desired
            application configuration.
        :param bytes hostname: The ascii encoded hostname of this node.
        """
        try:
            self['deployment_config'] = safe_load(deployment_config)
        except YAMLError as e:
            raise UsageError(
                "Deployment config could not be parsed as YAML:\n\n" + str(e)
            )
        try:
            self['app_config'] = safe_load(app_config)
        except YAMLError as e:
            raise UsageError(
                "Application config could not be parsed as YAML:\n\n" + str(e)
            )
        try:
            self['hostname'] = hostname.decode('ascii')
        except UnicodeDecodeError:
            raise UsageError(
                "Non-ascii hostname: {hostname}".format(hostname=hostname)
            )


@implementer(ICommandLineScript)
class ChangeStateScript(object):
    """
    A command to get a node into a desired state by pushing volumes, starting
    and stopping applications, opening up application ports and setting up
    routes to other nodes.
    """
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
