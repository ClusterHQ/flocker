# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script,flocker.node.functional.test_script -*- # noqa

"""
The command-line ``flocker-changestate``, ``flocker-reportstate`` and
``flocker-*-agent`` tools.
"""

import sys
from functools import partial

from yaml import safe_load, safe_dump
from yaml.error import YAMLError

from pyrsistent import PRecord, field

from zope.interface import implementer

from twisted.python.usage import Options, UsageError

from ..control._config import (
    FlockerConfiguration, marshal_configuration,
    )

from ..volume.service import (
    ICommandLineVolumeScript, VolumeScript)

from ..volume.script import flocker_volume_options
from ..common.script import (
    ICommandLineScript,
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from ..control import (
    ConfigurationError, current_from_configuration, model_from_configuration,
    NodeState
)
from . import P2PNodeDeployer, change_node_state
from ._loop import AgentLoopService
from .agents.blockdevice import LoopbackBlockDeviceAPI, BlockDeviceDeployer


__all__ = [
    "flocker_changestate_main",
    "flocker_reportstate_main",
    "flocker_zfs_agent_main",
    "flocker_dataset_agent_main",
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
        deployer = P2PNodeDeployer(
            options['hostname'].decode("ascii"),
            volume_service, self._docker_client)
        return change_node_state(deployer, options['deployment'],
                                 options['current'])


def flocker_changestate_main():
    return FlockerScriptRunner(
        script=VolumeScript(ChangeStateScript()),
        options=ChangeStateOptions(),
        logging=False,
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
        # Discovery doesn't actually care about hostname, so don't bother
        # figuring out correct one. Especially since this code is going
        # away someday soon: https://clusterhq.atlassian.net/browse/FLOC-1353
        deployer = P2PNodeDeployer(
            u"localhost",
            volume_service, self._docker_client, self._network)
        d = deployer.discover_local_state(NodeState(hostname=u"localhost"))
        d.addCallback(marshal_configuration)
        d.addCallback(safe_dump)
        d.addCallback(self._stdout.write)
        return d


def flocker_reportstate_main():
    return FlockerScriptRunner(
        script=VolumeScript(ReportStateScript()),
        options=ReportStateOptions(),
        logging=False,
    ).main()


@flocker_standard_options
@flocker_volume_options
class ZFSAgentOptions(Options):
    """
    Command line options for ``flocker-zfs-agent`` cluster management process.
    """
    longdesc = """\
    flocker-zfs-agent runs a ZFS-backed convergence agent on a node.
    """

    synopsis = (
        "Usage: flocker-zfs-agent [OPTIONS] <local-hostname> "
        "<control-service-hostname>")

    optParameters = [
        ["destination-port", "p", 4524,
         "The port on the control service to connect to.", int],
    ]

    def parseArgs(self, hostname, host):
        # Passing in the 'hostname' (really node identity) via command
        # line is a hack.  See
        # https://clusterhq.atlassian.net/browse/FLOC-1381 for solution.
        self["hostname"] = unicode(hostname, "ascii")
        self["destination-host"] = unicode(host, "ascii")


@implementer(ICommandLineVolumeScript)
class ZFSAgentScript(object):
    """
    A command to start a long-running process to manage volumes on one node of
    a Flocker cluster.
    """
    def main(self, reactor, options, volume_service):
        host = options["destination-host"]
        port = options["destination-port"]
        deployer = P2PNodeDeployer(options["hostname"].decode("ascii"),
                                   volume_service)
        loop = AgentLoopService(reactor=reactor, deployer=deployer,
                                host=host, port=port)
        volume_service.setServiceParent(loop)
        return main_for_service(reactor, loop)


def flocker_zfs_agent_main():
    return FlockerScriptRunner(
        script=VolumeScript(ZFSAgentScript()),
        options=ZFSAgentOptions()
    ).main()


@flocker_standard_options
class DatasetAgentOptions(Options):
    """
    Command line options for ``flocker-dataset-agent``.

    XXX: This is a hack. Better to have required options and to share the
    common options with ``ZFSAgentOptions``.
    """
    longdesc = """\
    flocker-dataset-agent runs a dataset convergence agent on a node.
    """

    synopsis = (
        "Usage: flocker-dataset-agent [OPTIONS] <local-hostname> "
        "<control-service-hostname>")

    optParameters = [
        ["destination-port", "p", 4524,
         "The port on the control service to connect to.", int],
    ]

    def parseArgs(self, hostname, host):
        # Passing in the 'hostname' (really node identity) via command
        # line is a hack.  See
        # https://clusterhq.atlassian.net/browse/FLOC-1381 for solution.
        self["hostname"] = unicode(hostname, "ascii")
        self["destination-host"] = unicode(host, "ascii")


@implementer(ICommandLineScript)
class DatasetAgentScript(PRecord):
    """
    Implement top-level logic for the ``flocker-dataset-agent`` script.

    :ivar service_factory: A two-argument callable that returns an ``IService``
        provider that will get run when this script is run.  The arguments
        passed to it are the reactor being used and a ``DatasetAgentOptions``
        instance which has parsed any command line options that were given.
    """
    service_factory = field(mandatory=True)

    def main(self, reactor, options):
        return main_for_service(
            reactor,
            self.service_factory(reactor, options)
        )


class DatasetAgentServiceFactory(PRecord):
    """
    Implement general agent setup in a way that's usable by
    ``DatasetAgentScript`` but also easily testable.

    Possibly ``ICommandLineScript`` should be replaced by something that is
    inherently more easily tested so that this separation isn't required.

    :ivar deployer_factory: A one-argument callable to create an ``IDeployer``
        provider for this script.  The one argument is the ``hostname`` keyword
        argument (it must be passed by keyword).
    """
    deployer_factory = field(mandatory=True)

    def get_service(self, reactor, options):
        """
        Create an ``AgentLoopService`` instance.

        :param reactor: The reactor to give to the service so it can schedule
            timed events and make network connections.

        :param DatasetAgentOptions options: The command-line options to use to
            configure the loop and the loop's deployer.

        :return: The ``AgentLoopService`` instance.
        """
        return AgentLoopService(
            reactor=reactor,
            deployer=self.deployer_factory(hostname=options["hostname"]),
            host=options["destination-host"], port=options["destination-port"],
        )


def flocker_dataset_agent_main():
    """
    Implementation of the ``flocker-dataset-agent`` command line script.

    This starts a dataset convergence agent.  It currently supports only the
    loopback block device backend.  Later it will be capable of starting a
    dataset agent using any of the support dataset backends.
    """
    # Later, construction of this object can be moved into
    # DatasetAgentServiceFactory.get_service where various options passed on
    # the command line could alter what is created and how it is initialized.
    api = LoopbackBlockDeviceAPI.from_path(
        b"/var/lib/flocker/loopback"
    )
    deployer_factory = partial(
        BlockDeviceDeployer,
        block_device_api=api,
    )
    service_factory = DatasetAgentServiceFactory(
        deployer_factory=deployer_factory
    ).get_service
    agent_script = DatasetAgentScript(
        service_factory=service_factory,
    )
    return FlockerScriptRunner(
        script=agent_script,
        options=DatasetAgentOptions()
    ).main()
