# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script,flocker.node.functional.test_script -*- # noqa

"""
The command-line ``flocker-*-agent`` tools.
"""

from functools import partial

from pyrsistent import PRecord, field

from zope.interface import implementer

from twisted.python.filepath import FilePath
from twisted.python.usage import Options

from ..volume.service import (
    ICommandLineVolumeScript, VolumeScript)

from ..volume.script import flocker_volume_options
from ..common.script import (
    ICommandLineScript,
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from . import P2PManifestationDeployer, ApplicationNodeDeployer
from ._loop import AgentLoopService
from .agents.blockdevice import LoopbackBlockDeviceAPI, BlockDeviceDeployer


__all__ = [
    "flocker_dataset_agent_main",
]

@flocker_standard_options
class _AgentOptions(Options):
    """
    Command line options for agents.

    XXX: This is a hack. Better to have required options and to share the
    common options with ``ZFSAgentOptions``.
    """
    # Use as basis for subclass' synopsis:
    synopsis = (
        "Usage: {} [OPTIONS] <local-hostname> "
        "<control-service-hostname>")

    optParameters = [
        ["destination-port", "p", 4524,
         "The port on the control service to connect to.", int],
    ]

    def parseArgs(self, hostname, host):
        # Passing in the 'hostname' (really node identity) via command
        # line is a hack.  See
        # https://clusterhq.atlassian.net/browse/FLOC-1381 for solution,
        # or perhaps https://clusterhq.atlassian.net/browse/FLOC-1631.
        self["hostname"] = unicode(hostname, "ascii")
        self["destination-host"] = unicode(host, "ascii")


class DatasetAgentOptions(_AgentOptions):
    """
    Command line options for ``flocker-dataset-agent``.
    """
    longdesc = """\
    flocker-dataset-agent runs a dataset convergence agent on a node.
    """

    synopsis = _AgentOptions.synopsis.format("flocker-dataset-agent")

    optParameters = [
        ["config-file", "c", FilePath("/etc/flocker/dataset-agent.yml"),
         "The configuration file for the dataset agent.", FilePath],
    ]


class ContainerAgentOptions(_AgentOptions):
    """
    Command line options for ``flocker-container-agent``.
    """
    longdesc = """\
    flocker-container-agent runs a container convergence agent on a node.
    """

    synopsis = _AgentOptions.synopsis.format("flocker-container-agent")


@implementer(ICommandLineScript)
class AgentScript(PRecord):
    """
    Implement top-level logic for the ``flocker-dataset-agent`` and
    ``flocker-container-agent`` scripts.

    :ivar service_factory: A two-argument callable that returns an ``IService``
        provider that will get run when this script is run.  The arguments
        passed to it are the reactor being used and a ``AgentOptions``
        instance which has parsed any command line options that were given.
    """
    service_factory = field(mandatory=True)

    def main(self, reactor, options):
        return main_for_service(
            reactor,
            self.service_factory(reactor, options)
        )


class AgentServiceFactory(PRecord):
    """
    Implement general agent setup in a way that's usable by
    ``AgentScript`` but also easily testable.

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

        :param AgentOptions options: The command-line options to use to
            configure the loop and the loop's deployer.

        :return: The ``AgentLoopService`` instance.
        """
        return AgentLoopService(
            reactor=reactor,
            deployer=self.deployer_factory(options=options),
            host=options["destination-host"], port=options["destination-port"],
        )


def volume_service_from_config(config):
    pass

def dataset_deployer_from_options(options):
    """
    Returns an IDeployer configured by options.
    """
    import yaml
    config = yaml.safe_load(options['config-file'].getContents())
    if config['backend'] == 'zfs':
        # TODO The volume service should be integrated with the reactor - see
        # main_for_service
        volume_service = VolumeService(
            config_path=flocker.volume.service.DEFAULT_CONFIG_PATH,
            pool=config.get('zfs-pool', flocker.volume.service.FLOCKER_POOL),
            # TODO thread through the reactor
            reactor=reactor,
        )

        deployer_factory = partial(
            P2PManifestationDeployer, volume_service=volume_service)
    elif config['backend'] == 'loopback':
        # Later, construction of this object can be moved into
        # AgentServiceFactory.get_service where various options passed on
        # the command line could alter what is created and how it is initialized.
        loopback_pool = config.get('loopback-pool',
                                   b"/var/lib/flocker/loopback")
        api = LoopbackBlockDeviceAPI.from_path(loopback_pool)
        deployer_factory = partial(
            BlockDeviceDeployer,
            block_device_api=api,
        )

    return deployer_factory(hostname=options['hostname'])


def flocker_dataset_agent_main():
    """
    Implementation of the ``flocker-dataset-agent`` command line script.

    This starts a dataset convergence agent.  It currently supports only the
    loopback block device backend.  Later it will be capable of starting a
    dataset agent using any of the support dataset backends.
    """
    service_factory = AgentServiceFactory(
        deployer_factory=dataset_deployer_from_options
    ).get_service
    agent_script = AgentScript(
        service_factory=service_factory,
    )
    return FlockerScriptRunner(
        script=agent_script,
        options=DatasetAgentOptions()
    ).main()


def flocker_container_agent_main():
    """
    Implementation of the ``flocker-container-agent`` command line script.

    This starts a Docker-based container convergence agent.
    """
    service_factory = AgentServiceFactory(
        # TODO this needs to be something which parses Options
        deployer_factory=ApplicationNodeDeployer
    ).get_service
    agent_script = AgentScript(service_factory=service_factory)
    return FlockerScriptRunner(
        script=agent_script,
        options=ContainerAgentOptions()
    ).main()
