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
import sys
from os import environ, getpid
from pprint import pprint
from uuid import UUID
from itertools import cycle

from pyrsistent import pmap

from eliot import add_destination

from twisted.internet.task import react, cooperate
from twisted.python.filepath import FilePath
from twisted.web.http import OK, CREATED
from twisted.python.log import err

from flocker.apiclient import FlockerClient
from flocker.common import gather_deferreds

NUM_CONTAINERS = NUM_DATASETS = 1


def stdout(message):
    sys.stdout.write(json.dumps(message) + "\n")
# add_destination(stdout)


def run_ops(jobs):
    # Execute some jobs concurrently so things go quickly but don't necessarily
    # completely overwhelm the server.
    workers = list(cooperate(jobs).whenDone().addErrback(err) for i in range(1000))
    return gather_deferreds(workers)


class MoreFlockerClient(FlockerClient):
    def list_nodes(self):
        return self._request(b"GET", b"/state/nodes", None, {OK})

    def list_containers_state(self):
        return self._request(b"GET", b"/state/containers", None, {OK})

    def list_containers_configuration(self):
        return self._request(b"GET", b"/configuration/containers", None, {OK})

    def create_container(self, node_uuid, name, image):
        return self._request(
            b"POST", b"/configuration/containers",
            dict(
                node_uuid=unicode(node_uuid), name=name, image=image
            ), {CREATED},
        )


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
        host = environ.get('FLOCKER_ACCEPTANCE_CONTROL_NODE_PRIVATE')
        control_node_uuid = [
            node['uuid']
            for node in nodes
            if node['host'] == host
        ][0]
        return control_node_uuid

    return d.addCallback(identify_control_node)


def create_datasets(client):
    d = gather_deferreds((
        client.list_nodes(),
        client.list_datasets_configuration(),
    ))

    def pick_nodes((nodes, datasets)):
        # Pick the two nodes with the fewest datasets
        count_to_node = {}
        for dataset in datasets:
            if dataset.primary is not None:
                count_to_node[dataset.primary] = (
                    count_to_node.get(dataset.primary, 0) + 1
                )
        return sorted(
            nodes,
            key=lambda node: (
                count_to_node.get(node["uuid"], 0),
                node["uuid"],
            ),
        )[:2]
    d.addCallback(pick_nodes)

    def create(nodes):
        primary_node_uuids = [
            UUID(node['uuid'].encode('ascii')) for node in nodes
        ]

        maximum_size = int(
            environ.get(
                'FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE'
            )
        )

        def _create(client, count, primaries):
            for primary_node_uuid in primaries:
                for i in range(count / len(primaries)):
                    yield client.create_dataset(
                        primary=primary_node_uuid,
                        maximum_size=maximum_size,
                    )

        return run_ops(_create(client, NUM_DATASETS, primary_node_uuids))

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
    d = client.list_datasets_configuration()

    def delete(datasets):
        deleted = [
            client.delete_dataset(dataset.dataset_id)
            for dataset in datasets
        ]
        return gather_deferreds(deleted)
    d.addCallback(delete)
    d.addCallback(output)
    return d


def print_node_state(client):
    d = client.list_nodes()
    d.addCallback(output)
    return d


def create_containers(client):
    d = gather_deferreds((
        client.list_nodes(),
        client.list_containers_state(),
    ))

    def pick_nodes((nodes, containers)):
        return nodes
        # Pick the two nodes with the fewest datasets
        count_to_node = {}
        for container in containers:
            node_uuid = container["node_uuid"]
            count_to_node[node_uuid] = (
                count_to_node.get(node_uuid, 0) + 1
                )
        return sorted(
            nodes,
            key=lambda node: (
                count_to_node.get(node["uuid"], 0),
                node["uuid"],
            ),
        )[:2]
    d.addCallback(pick_nodes)

    def create(nodes):
        primary_node_uuids = [
            UUID(node['uuid'].encode('ascii')) for node in nodes
        ]

        def _create(client, count, primaries):
            primary_cycle = cycle(primaries)
            for i, primary_node_uuid in enumerate(primary_cycle):
                if i == count:
                    break

                yield client.create_container(
                    node_uuid=primary_node_uuid,
                    name=u"{pid}-{counter}".format(
                        pid=getpid(), counter=i,
                    ),
                    image=u"openshift/busybox-http-app",
                )
                print 'Configured container', i

        creating = list(_create(client, NUM_CONTAINERS, primary_node_uuids))

        return gather_deferreds(creating)

    d.addCallback(create)
    return d


def print_containers_state(client, verbose=False):
    def report(state):
        if verbose:
            pprint(state)
        print(len(state))
    return client.list_containers_state().addCallback(report)


def print_containers_configuration(client, verbose=False):
    def report(config):
        if verbose:
            pprint(config)
        print(len(config))
    return client.list_containers_configuration().addCallback(report)


def delete_containers(client):
    d = client.list_containers_configuration()

    def delete(containers):
        for container in containers:
            yield client._request(
                b"DELETE",
                b"/configuration/containers/" + container["name"].encode("ascii"),
                None, {OK}
            )
    d.addCallback(delete)
    d.addCallback(run_ops)
    return d


def print_diverged_containers(client):
    d = gather_deferreds((
        client.list_containers_configuration(),
        client.list_containers_state(),
    ))

    def compare((configuration, state)):
        comparable_state = set(
            pmap(container).remove(u"running").remove(u"restart_policy")
            for container in state
        )
        comparable_configuration = set(
            pmap(container).remove(u"restart_policy")
            for container in configuration
        )

        configured_not_running = comparable_configuration - comparable_state
        running_not_configured = comparable_state - comparable_configuration

        print "Configured but not running:"
        pprint(configured_not_running)

        print "Running but not configured:"
        pprint(running_not_configured)

    d.addCallback(compare)
    return d


operations = dict(
    print_node_state=print_node_state,
    print_datasets_state=print_datasets_state,
    print_datasets_configuration=print_datasets_configuration,
    create_datasets=create_datasets,
    delete_datasets=delete_datasets,
    create_containers=create_containers,
    print_containers_state=print_containers_state,
    print_containers_configuration=print_containers_configuration,
    delete_containers=delete_containers,
    print_diverged_containers=print_diverged_containers,
)


def main(reactor):
    client = flocker_client_from_environment(reactor)
    operation_name = sys.argv[1]
    d = operations[operation_name](client, *sys.argv[2:])
    return d


if __name__ == '__main__':
    react(main)
