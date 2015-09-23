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


def control_node_uuid(client):
    d = client.list_nodes()

    def identify_control_node(nodes):
        host = environ.get('FLOCKER_ACCEPTANCE_CONTROL_NODE')
        control_node_uuid = [
            node['uuid']
            for node in nodes
            if node['host'] == host
        ][0]
        return control_node_uuid

    return d.addCallback(identify_control_node)


def create_datasets(client):
    d = control_node_uuid(client)

    def create(control_node_uuid):
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

    d.addCallback(create)
    return d


def output(datasets):
    for dataset in datasets:
        print dataset


def print_datasets_state(client):
    d = client.list_datasets_state()
    d.addCallback(output)
    return d


def print_datasets_configuration(client):
    d = client.list_datasets_configuration()
    d.addCallback(output)
    return d


def delete_datasets(client):
    d = client.list_datasets_state()

    def delete(datasets):
        deleted = [
            client.delete_dataset(dataset.dataset_id)
            for dataset in datasets
        ]
        return gather_deferreds(deleted)
    d.addCallback(delete)
    d.addCallback(output)
    return d


operations = dict(
    print_datasets_state=print_datasets_state,
    print_datasets_configuration=print_datasets_configuration,
    create_datasets=create_datasets,
    delete_datasets=delete_datasets,
)


def main(reactor):
    client = flocker_client_from_environment(reactor)
    operation_name = sys.argv[1]
    d = operations[operation_name](client)
    return d


if __name__ == '__main__':
    react(main)
