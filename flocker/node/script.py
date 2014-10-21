# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script -*-

"""
The command-line ``flocker-changestate`` and ``flocker-reportstate``
tools.
"""

import sys

from twisted.python.usage import Options, UsageError
from twisted.internet.defer import Deferred, maybeDeferred

from yaml import safe_load, safe_dump
from yaml.error import YAMLError

from zope.interface import implementer

from ._config import marshal_configuration

from ..volume.service import (
    ICommandLineVolumeScript, VolumeScript)
from ..volume.script import flocker_volume_options
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner)
from . import (ConfigurationError, model_from_configuration, Deployer,
               FlockerConfiguration, current_from_configuration)

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
            configuration = FlockerConfiguration(application_config)
            parsed_applications = configuration.applications()
            self['deployment'] = model_from_configuration(
                applications=parsed_applications,
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
        :param DockerClient docker_client: The object to use to talk to the
            Docker server.
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

    def __init__(self, docker_client=None, network=None):
        """
        :param DockerClient docker_client: The object to use to talk to the
            Docker server.

        :param INetwork network: The object to use to interact with the node's
            network configuration.
        """
        self._docker_client = docker_client
        self._network = network

    def main(self, reactor, options, volume_service):
        deployer = Deployer(volume_service, self._docker_client, self._network)
        d = deployer.discover_node_configuration()
        d.addCallback(marshal_configuration)
        d.addCallback(safe_dump)
        d.addCallback(self._stdout.write)
        return d


def flocker_reportstate_main():
    return FlockerScriptRunner(
        script=VolumeScript(ReportStateScript()),
        options=ReportStateOptions()
    ).main()


def _chain_stop_result(service, stop):
    """
    Stop a service and chain the resulting ``Deferred`` to another
    ``Deferred``.

    :param IService service: The service to stop.
    :param Deferred stop: The ``Deferred`` which will be fired when the service
        has stopped.
    """
    maybeDeferred(service.stopService).chainDeferred(stop)


def _main_for_service(reactor, service):
    """
    Start a service and integrate its shutdown with reactor shutdown.

    This is useful for hooking driving an ``IService`` provider with
    ``twisted.internet.task.react``.  For example::

        from twisted.internet.task import react
        from yourapp import YourService
        react(_main_for_service, [YourService()])

    :param IReactorCore reactor: The reactor the run lifetime of which to tie
        to the given service.  When the reactor is shutdown, the service will
        be shutdown.

    :param IService service: The service to tie to the run lifetime of the
        given reactor.  It will be started immediately and made to stop when
        the reactor stops.

    :return: A ``Deferred`` which fires after the service has finished
        stopping.
    """
    service.startService()
    stop = Deferred()
    reactor.addSystemEventTrigger("before", "shutdown", _chain_stop_result, service, stop)
    return stop
