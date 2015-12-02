from ipaddr import IPAddress
import json

import yaml

from twisted.python.filepath import FilePath

from flocker.apiclient import FlockerClient


class BenchmarkCluster:

    def __init__(
        self, control_node_address, ca_cert_path, cert_path,
        key_path, public_addresses
    ):
        self._control_node_address = control_node_address
        self.ca_cert_path = ca_cert_path
        self.cert_path = cert_path
        self.key_path = key_path
        self._public_addresses = public_addresses

        self._control_service = None

    @classmethod
    def from_acceptance_test_env(cls, env):
        certs = FilePath(env['FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH'])
        ca_cluster_path = certs.child(b"cluster.crt")
        cert_path = certs.child(b"user.crt")
        key_path = certs.child(b"user.key")
        host_to_public = json.loads(
            env['FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS']
        )
        public_addresses = {
            IPAddress(k): IPAddress(v) for k, v in host_to_public.items()
        }
        return cls(
            env['FLOCKER_ACCEPTANCE_CONTROL_NODE'], ca_cluster_path, cert_path,
            key_path, public_addresses
        )

    @classmethod
    def from_uft_setup(cls, uft):
        ca_cluster_path = uft.child(b"cluster.crt")
        cert_path = uft.child(b"user.crt")
        key_path = uft.child(b"user.key")
        with open(uft.child('cluster.yml'), 'rt') as f:
            cluster = yaml.safe_load(f)
        host_to_public = {
            node['private']: node['public'] for node in cluster['agent_nodes']
        }
        public_addresses = {
            IPAddress(k): IPAddress(v) for k, v in host_to_public.items()
        }
        return cls(
            cluster['control-node'], ca_cluster_path, cert_path,
            key_path, public_addresses
        )

    def control_node_address(self):
        return self._control_node_address

    def control_service(self, reactor):
        control_service = self._control_service
        if control_service is None:
            control_service = self._control_service = FlockerClient(
                reactor,
                host=self._control_node_address,
                port=4523,
                ca_cluster_path=self.ca_cert_path,
                cert_path=self.cert_path,
                key_path=self.key_path,
            )
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


class FakeBenchmarkCluster:

    def __init__(
        self, control_node_address, control_service, public_addresses={}
    ):
        self._control_node_address = control_node_address
        self._control_service = control_service
        self._public_addresses = public_addresses

    def control_node_address(self):
        return self._control_node_address

    def control_service(self, reactor):
        return self._control_service

    def public_address(self, hostname):
        """
        Convert a node's internal hostname to a public address.  If the
        hostname does not exist in ``_public_addresses``, just return the
        hostname, and hope it is public.

        :param IPAddress hostname: Hostname for Flocker node.
        :return IPAddress: Public IP address for node.
        """
        return self._public_addresses.get(hostname, hostname)
