# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script,flocker.node.functional.test_script -*- # noqa

"""
The command-line ``flocker-*-agent`` tools.
"""

from functools import partial
from socket import socket
from os import getpid

import yaml

from jsonschema import FormatChecker, Draft4Validator

from pyrsistent import PRecord, field

from zope.interface import implementer

from twisted.python.filepath import FilePath
from twisted.python.usage import Options

from ..volume.service import (
    ICommandLineVolumeScript, VolumeScript,
)

from ..volume.script import flocker_volume_options
from ..common.script import (
    ICommandLineScript,
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from . import P2PManifestationDeployer, ApplicationNodeDeployer
from ._loop import AgentLoopService
from .agents.blockdevice import LoopbackBlockDeviceAPI, BlockDeviceDeployer
from ..control._model import ip_to_uuid


__all__ = [
    "flocker_dataset_agent_main",
]


def _get_external_ip(host, port):
    """
    Get an external IP address for this node that can in theory connect to
    the given host and port.

    See https://clusterhq.atlassian.net/browse/FLOC-1751 for better solution.
    :param host: A host to connect to.
    :param port: The port to connect to.

    :return unicode: IP address of external interface on this node.
    """
    sock = socket()
    try:
        sock.setblocking(False)
        sock.connect_ex((host, port))
        return unicode(sock.getsockname()[0], "ascii")
    finally:
        sock.close()


def validate_configuration(configuration):
    """
    Validate a provided configuration.

    :param dict configuration: A desired configuration for an agent.

    :raises: jsonschema.ValidationError if the configuration is invalid.
    """
    # XXX Create a function which loads and validates, and also setting
    # defaults. FLOC-1791.
    schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "required": ["version", "control-service", "dataset"],
        "properties": {
            "version": {
                "type": "number",
                "maximum": 1,
                "minimum": 1,
            },
            "control-service": {
                "type": "object",
                "required": ["hostname"],
                "properties": {
                    "hostname": {
                        "type": "string",
                        "format": "hostname",
                    },
                    "port": {"type": "integer"},
                }
            },
            "dataset": {
                "type": "object",
                "oneOf": [
                    {
                        "required": ["backend"],
                        "properties": {
                            "backend": {
                                "type": "string",
                                "pattern": "zfs",
                            },
                            "pool": {
                                "type": "string",
                            },
                        }
                    },
                    {
                        "required": ["backend"],
                        "properties": {
                            "backend": {
                                "type": "string",
                                "pattern": "loopback",
                            },
                            "pool": {
                                "type": "string",
                            },
                        }

                    },
                ]
            }
        }
    }

    v = Draft4Validator(schema, format_checker=FormatChecker())
    v.validate(configuration)


@flocker_standard_options
@flocker_volume_options
class _AgentOptions(Options):
    """
    Command line options for agents.
    """
    # Use as basis for subclass' synopsis:
    synopsis = "Usage: {} [OPTIONS]"

    optParameters = [
        ["agent-config", "c", "/etc/flocker/agent.yml",
         "The configuration file to set the control service."],
    ]

    def postOptions(self):
        self['agent-config'] = FilePath(self['agent-config'])


class DatasetAgentOptions(_AgentOptions):
    """
    Command line options for ``flocker-dataset-agent``.
    """
    longdesc = """\
    flocker-dataset-agent runs a dataset convergence agent on a node.
    """

    synopsis = _AgentOptions.synopsis.format("flocker-dataset-agent")


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

    :ivar deployer_factory: A two-argument callable to create an
        ``IDeployer`` provider for this script.  The arguments are a
        ``hostname`` keyword argument and a ``node_uuid`` keyword
        argument. They must be passed by keyword.
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
        agent_config = options[u'agent-config']
        configuration = yaml.safe_load(agent_config.getContent())

        validate_configuration(configuration=configuration)

        host = configuration['control-service']['hostname']
        port = configuration['control-service'].get('port', 4524)
        ip = _get_external_ip(host, port)

        deployer = self.deployer_factory(
            dataset_configuration=configuration['dataset'],
            node_uuid=ip_to_uuid(ip),
            hostname=ip)

        return AgentLoopService(
            reactor=reactor,
            # Temporary hack, to be fixed in FLOC-1783 probably:
            deployer=deployer,
            host=host, port=port,
        )


def zfs_dataset_deployer(volume_service):
    """
    This should be changed significantly as part of refactoring in
    FLOC-1791.
    """
    return partial(
        P2PManifestationDeployer,
        volume_service=volume_service,
    )


def loopback_dataset_deployer(volume_service):
    """
    This should be changed significantly as part of refactoring in
    FLOC-1791.
    """
    # Later, construction of this object can be moved into
    # AgentServiceFactory.get_service where various options passed on
    # the command line could alter what is created and how it is initialized.
    api = LoopbackBlockDeviceAPI.from_path(
        b"/var/lib/flocker/loopback",
        # Make up a new value every time this script starts.  This will ensure
        # different instances of the script using this backend always appear to
        # be running on different nodes (as far as attachment is concerned).
        # This is a good thing since it makes it easy to simulate a multi-node
        # cluster by running multiple instances of the script.  Similar effect
        # could be achieved by making this id a command line argument but that
        # would be harder to implement and harder to use.
        compute_instance_id=bytes(getpid()).decode('utf-8'),
    )
    return partial(
        BlockDeviceDeployer,
        block_device_api=api,
    )

def dataset_deployer_from_configuration(dataset_configuration, volume_service,
    node_uuid, hostname):
    backend_to_deployer_factory = {
        'zfs': zfs_dataset_deployer,
        'loopback': loopback_dataset_deployer,
    }
    backend = dataset_configuration['backend']
    deployer_factory = backend_to_deployer_factory[backend]
    deployer_factory_partial = deployer_factory(
        volume_service=volume_service
    )
    return deployer_factory_partial(node_uuid=node_uuid, hostname=hostname)

@implementer(ICommandLineVolumeScript)
class AgentScriptFactory(PRecord):
    """
    This code is temporary, and will probably be changed significantly and
    moved into AgentScript. It isn't really a factory. FLOC-1791.
    """
    def main(self, reactor, options, volume_service):
        deployer_factory = partial(
            dataset_deployer_from_configuration,
            volume_service=volume_service,
        )

        service_factory = AgentServiceFactory(
            deployer_factory=deployer_factory
        ).get_service

        service = service_factory(reactor, options)

        agent_config = options[u'agent-config']
        configuration = yaml.safe_load(agent_config.getContent())
        validate_configuration(configuration=configuration)
        if configuration['dataset']['backend'] == 'zfs':
            volume_service.setServiceParent(service)

        return main_for_service(
            reactor=reactor,
            service=service,
        )


def flocker_dataset_agent_main():
    """
    Implementation of the ``flocker-dataset-agent`` command line script.

    This starts a dataset convergence agent.  It currently supports only the
    loopback block device backend.  Later it will be capable of starting a
    dataset agent using any of the support dataset backends.
    """
    options = DatasetAgentOptions()

    return FlockerScriptRunner(
        script=VolumeScript(AgentScriptFactory()),
        options=options,
    ).main()


def flocker_container_agent_main():
    """
    Implementation of the ``flocker-container-agent`` command line script.

    This starts a Docker-based container convergence agent.
    """
    service_factory = AgentServiceFactory(
        deployer_factory=ApplicationNodeDeployer
    ).get_service
    agent_script = AgentScript(service_factory=service_factory)
    return FlockerScriptRunner(
        script=agent_script,
        options=ContainerAgentOptions()
    ).main()
