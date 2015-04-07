# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script,flocker.node.functional.test_script -*- # noqa

"""
The command-line ``flocker-*-agent`` tools.
"""

from functools import partial

from pyrsistent import PRecord, field

from zope.interface import implementer

from twisted.python.usage import Options

from ..volume.service import (
    ICommandLineVolumeScript, VolumeScript)

from ..volume.script import flocker_volume_options
from ..common.script import (
    ICommandLineScript,
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from . import P2PNodeDeployer
from ._loop import AgentLoopService
from .agents.blockdevice import LoopbackBlockDeviceAPI, BlockDeviceDeployer


__all__ = [
    "flocker_zfs_agent_main",
    "flocker_dataset_agent_main",
]


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
