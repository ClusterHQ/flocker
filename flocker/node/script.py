# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script -*-

"""
The command-line ``flocker-changestate`` and ``flocker-reportstate``
tools.
"""

import sys

from twisted.python.usage import Options, UsageError

from yaml import safe_load
from yaml.error import YAMLError

from zope.interface import implementer

from ._config import configuration_to_yaml

from ..volume.service import (
    ICommandLineVolumeScript, VolumeScript)
from ..volume.script import flocker_volume_options
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner)
from . import (ConfigurationError, model_from_configuration, Deployer,
               current_from_configuration)

__all__ = [
    "ChangeStateOptions",
    "ChangeStateScript",
    "flocker_changestate_main",
    "ReportStateOptions",
    "ReportStateScript",
    "flocker_reportstate_main",
]


@flocker_standard_options
@flocker_volume_options
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

    * current_configuration: The YAML string describing the current
        cluster configuration.

    * hostname: The hostname of this node. Used by the node to identify which
        applications from deployment_configuration should be running.
    """
    synopsis = ("Usage: flocker-changestate [OPTIONS] "
                "<deployment configuration> <application configuration> "
                "<cluster configuration> <hostname>")

    def parseArgs(self, deployment_config, application_config, current_config,
                  hostname):
        """
        Parse `deployment_config`, `application_config` and `current_config`
        strings as YAML, and into a :class:`Deployment` instance. Assign
        the resulting instance to this `Options` dictionary. Decode a
        supplied hostname as ASCII and assign to a `hostname` key.

        :param bytes deployment_config: The YAML string describing the desired
            deployment configuration.

        :param bytes application_config: The YAML string describing the desired
            application configuration.

        :param bytes current_config: The YAML string describing the current
            cluster configuration.

        :param bytes hostname: The ascii encoded hostname of this node.

        :raises UsageError: If the configuration files cannot be parsed as YAML
            or if the hostname can not be decoded as ASCII.
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
            current_config = safe_load(current_config)
        except YAMLError as e:
            raise UsageError(
                "Current config could not be parsed as YAML:\n\n" + str(e)
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
        # Current configuration is not written by a human, so don't bother
        # with nice error for failure to parse:
        self["current"] = current_from_configuration(current_config)


@implementer(ICommandLineVolumeScript)
class ChangeStateScript(object):
    """
    A command to get a node into a desired state by pushing volumes, starting
    and stopping applications, opening up application ports and setting up
    routes to other nodes.

    :ivar DockerClient _docker_client: See the ``docker_client`` parameter to
        ``__init__``.
    """
    def __init__(self, docker_client=None):
        """
        :param DockerClient docker_client: The object to use to talk to the Gear
            server.
        """
        self._docker_client = docker_client

    def main(self, reactor, options, volume_service):
        deployer = Deployer(volume_service, self._docker_client)
        return deployer.change_node_state(
            desired_state=options['deployment'],
            current_cluster_state=options['current'],
            hostname=options['hostname']
        )


def flocker_changestate_main():
    return FlockerScriptRunner(
        script=VolumeScript(ChangeStateScript()),
        options=ChangeStateOptions()
    ).main()


@flocker_standard_options
@flocker_volume_options
class ReportStateOptions(Options):
    """
    Command line options for ``flocker-reportstate`` management tool.
    """

    longdesc = """\
    flocker-reportstate is called by flocker-deploy to get the configuration of
    a node.
    """
    synopsis = ("Usage: flocker-reportstate [OPTIONS]")


@implementer(ICommandLineVolumeScript)
class ReportStateScript(object):
    """
    A command to return the state of a node.

    :ivar DockerClient _docker_client: See the ``docker_client`` parameter to
        ``__init__``.
    """
    _stdout = sys.stdout

    def __init__(self, docker_client=None):
        """
        :param DockerClient docker_client: The object to use to talk to the Gear
            server.
        """
        self._docker_client = docker_client

    def _print_yaml(self, result):
        self._stdout.write(result)

    def main(self, reactor, options, volume_service):
        deployer = Deployer(volume_service, self._docker_client)
        d = deployer.discover_node_configuration()
        d.addCallback(lambda state: configuration_to_yaml(
            list(state.running + state.not_running)))
        d.addCallback(self._print_yaml)
        return d


def flocker_reportstate_main():
    return FlockerScriptRunner(
        script=VolumeScript(ReportStateScript()),
        options=ReportStateOptions()
    ).main()
