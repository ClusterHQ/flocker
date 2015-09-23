# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
export FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE=107374182400;
export FLOCKER_ACCEPTANCE_CONTROL_NODE=119.9.72.122;
export FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS='{}';
export FLOCKER_ACCEPTANCE_VOLUME_BACKEND=openstack;
export FLOCKER_ACCEPTANCE_NUM_AGENT_NODES=10;
export FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH=/tmp/tmpS5dIHs;
"""
import json
from os import environ
import sys
from uuid import UUID

from eliot import add_destination

from twisted.internet.task import react
from twisted.python.filepath import FilePath
from twisted.web.http import OK

from flocker.apiclient import FlockerClient
from flocker.common import gather_deferreds


def stdout(message):
    sys.stdout.write(json.dumps(message) + "\n")
add_destination(stdout)


class MoreFlockerClient(FlockerClient):
    def list_nodes(self):
        return self._request(b"GET", b"/state/nodes", None, {OK})


def flocker_client_from_environment(reactor):
    host = environ.get('FLOCKER_ACCEPTANCE_CONTROL_NODE')
    certificates_directory = FilePath(
        environ.get('FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH')
    )
    return MoreFlockerClient(
        reactor=reactor,
        host=host,
        port=4523,
        ca_cluster_path=certificates_directory.child('cluster.crt'),
        cert_path=certificates_directory.child('user.crt'),
        key_path=certificates_directory.child('user.key'),
    )


def main(reactor):
    client = flocker_client_from_environment(reactor)
    listing_nodes = client.list_nodes()

    def create_datasets(nodes):
        host = environ.get('FLOCKER_ACCEPTANCE_CONTROL_NODE')
        control_node_uuid = [
            node['uuid']
            for node in nodes
            if node['host'] == host
        ][0]
        primary = UUID(control_node_uuid.encode('ascii'))
        maximum_size = int(
            environ.get(
                'FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE'
            )
        )

        creating = list(
            client.create_dataset(
                primary=primary,
                maximum_size=maximum_size,
            ) for i in range(20)
        )
        return gather_deferreds(creating)

    creating_nodes = listing_nodes.addCallback(create_datasets)

    return creating_nodes

if __name__ == '__main__':
    react(main)
