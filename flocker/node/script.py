# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script -*-

"""
The command-line ``flocker-changestate`` and ``flocker-reportstate``
tools.
"""

import sys

from twisted.python.usage import Options, UsageError
from twisted.internet import reactor

from yaml import safe_load
from yaml.error import YAMLError

from zope.interface import implementer

from ._config import configuration_to_yaml

from ..volume.script import VolumeOptions, VolumeScript
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, ICommandLineScript)
from . import ConfigurationError, model_from_configuration, Deployer

__all__ = [
    "ChangeStateOptions",
    "ChangeStateScript",
    "flocker_changestate_main",
    "ReportStateOptions",
    "ReportStateScript",
    "flocker_reportstate_main",
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
        into a :class:`Deployment` instance. Assign the resulting instance to
        this `Options` dictionary. Decode a supplied hostname as ASCII and
        assign to a `hostname` key.

        :param bytes deployment_config: The YAML string describing the desired
            deployment configuration.
        :param bytes application_config: The YAML string describing the desired
            application configuration.
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


def _default_volume_service():
    """
    Create a ``VolumeService`` using the default configuration.

    :return: A ``VolumeService``.
    """
    options = VolumeOptions()
    options.postOptions()
    return VolumeScript().create_volume_service(reactor, options)


@implementer(ICommandLineScript)
class ChangeStateScript(object):
    """
    A command to get a node into a desired state by pushing volumes, starting
    and stopping applications, opening up application ports and setting up
    routes to other nodes.

    :ivar Deployer _deployer: A :class:`Deployer` instance used to change the
        state of the current node.
    """
    def __init__(self, create_volume_service=_default_volume_service):
        """
        :param create_volume_service: Callable that returns a
            ``VolumeService``, defaulting to a standard production-configured
            service.
        """
        self._deployer = Deployer(create_volume_service())

    def main(self, reactor, options):
        """
        See :py:meth:`ICommandLineScript.main` for parameter documentation.
        """
        return self._deployer.change_node_state(
            desired_state=options['deployment'],
            hostname=options['hostname']
        )


def flocker_changestate_main():
    return FlockerScriptRunner(
        script=ChangeStateScript(),
        options=ChangeStateOptions()
    ).main()


@flocker_standard_options
class ReportStateOptions(Options):
    """
    Command line options for ``flocker-reportstate`` management tool.
    """

    longdesc = """\
    flocker-reportstate is called by flocker-deploy to get the configuration of
    a node.
    """
    synopsis = ("Usage: flocker-reportstate [OPTIONS]")


@implementer(ICommandLineScript)
class ReportStateScript(object):
    """
    A command to return the state of a node.

    :ivar Deployer _deployer: A :class:`Deployer` instance used to change the
        state of the current node.
    """
    def __init__(self,
                 create_volume_service=_default_volume_service,
                 create_volume_service_args=[],
                 gear_client=None):
        """
        :param create_volume_service: Callable that returns a
            ``VolumeService``, defaulting to a standard production-configured
            service.

        :param create_volume_service_args: A ``list`` of arguments to be
            passed to the create_volume_service callable, optional.

        :param gear_client: A ``GearClient`` instance, optional.

        """
        self._deployer = Deployer(
            create_volume_service(*create_volume_service_args),
            gear_client
        )

    def _print_yaml(self, result):
        sys.stdout.write(result)

    def main(self, reactor, options):
        """
        See :py:meth:`ICommandLineScript.main` for parameter documentation.
        """
        d = self._deployer.discover_node_configuration()
        d.addCallback(configuration_to_yaml)
        d.addCallback(self._print_yaml)
        return d


def flocker_reportstate_main():
    return FlockerScriptRunner(
        script=ReportStateScript(),
        options=ReportStateOptions()
    ).main()
