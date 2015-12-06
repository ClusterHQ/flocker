# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

from functools import partial
from ipaddr import IPAddress
import json

from jsonschema import FormatChecker, Draft4Validator
import yaml

from twisted.python.filepath import FilePath

from flocker.apiclient import FlockerClient


def validate_cluster_configuration(cluster_config):
    """
    Validate a provided cluster configuration.

    :param dict cluster_config: The cluster configuration.
    :raises: jsonschema.ValidationError if the configuration is invalid.
    """
    schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "required": ["control_node", "agent_nodes"],
        "properties": {
            "control_node": {
                "type": "string",
            },
            "agent_nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["public", "private"],
                    "properties": {
                        "public": {
                            "type": "string"
                        },
                        "private": {
                            "type": "string"
                        },
                    },
                },
            },
        },
        "additionalProperties": "true",
    }

    v = Draft4Validator(schema, format_checker=FormatChecker())
    v.validate(cluster_config)


class BenchmarkCluster:
    """
    Cluster for benchmark performance.

    :ivar str control_node_address: IP address for control service.
    :ivar control_service_factory: Callable taking a reactor parameter,
        and returning a IFlockerAPIV1Client.
    """

    def __init__(
        self, control_node_address, control_service_factory, public_addresses
    ):
        self._control_node_address = control_node_address
        self._control_service_factory = control_service_factory
        self._public_addresses = public_addresses

        self._control_service = None

    @classmethod
    def from_acceptance_test_env(cls, env):
        """
        Create a cluster from acceptance test environment variables.

        :param dict env: Dictionary mapping acceptance test environment names
            to values.
        :return: A ``BenchmarkCluster`` instance.
        """
        control_node_address = env['FLOCKER_ACCEPTANCE_CONTROL_NODE']
        certs = FilePath(env['FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH'])
        host_to_public = json.loads(
            env['FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS']
        )
        public_addresses = {
            IPAddress(k): IPAddress(v) for k, v in host_to_public.items()
        }
        control_service = partial(
            FlockerClient,
            host=control_node_address,
            port=4523,
            ca_cluster_path=certs.child('cluster.crt'),
            cert_path=certs.child('user.crt'),
            key_path=certs.child('user.key')
        )
        return cls(control_node_address, control_service, public_addresses)

    @classmethod
    def from_cluster_yaml(cls, path):
        """
        Create a cluster from Quick Start Installer files.

        :param FilePath path: directory containing Quick Start Installer
            ``cluster.yml`` and certificate files.
        :return: A ``BenchmarkCluster`` instance.
        """
        with path.child('cluster.yml').open() as f:
            cluster = yaml.safe_load(f)
        validate_cluster_configuration(cluster)
        control_node_address = cluster['control_node']
        public_addresses = {
            IPAddress(node['private']): IPAddress(node['public'])
            for node in cluster['agent_nodes']
        }
        control_service = partial(
            FlockerClient,
            host=control_node_address,
            port=4523,
            ca_cluster_path=path.child('cluster.crt'),
            cert_path=path.child('user.crt'),
            key_path=path.child('user.key')
        )
        return cls(control_node_address, control_service, public_addresses)

    def control_node_address(self):
        return self._control_node_address

    def control_service(self, reactor):
        control_service = self._control_service
        if control_service is None:
            control_service = self._control_service_factory(reactor)
            self._control_service = control_service
        return control_service

    def public_address(self, hostname):
        """
        Convert a node's internal hostname to a public address.  If the
        hostname does not exist in ``_public_addresses``, just return the
        hostname, and hope it is public.

        :param IPAddress hostname: Hostname for Flocker node.
        :return IPAddress: Public IP address for node.
        """
        return self._public_addresses.get(hostname, hostname)
