
import sys

from itertools import repeat

from twisted.internet.defer import inlineCallbacks
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from flocker.apiclient import FlockerClient
from flocker.common import gather_deferreds, loop_until
from flocker.control.httpapi import REST_API_PORT


class ScriptOptions(Options):
    optParameters = [
        ['control-node', None, None,
         "The address of the cluster's control node"],
        ['cert-directory', None, None,
         "The directory containing the cluster certificates"],
        ['timeout', None, 300,
         "The timeout in seconds for waiting until the operation is complete",
         int],
    ]

    def postOptions(self):
        if not self['control-node']:
            raise UsageError("Control node address must be provided.")
        if not self['cert-directory']:
            raise UsageError("Certificates directory must be provided.")


def main(reactor, args, base_path, top_level):
    try:
        options = ScriptOptions()
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write(e.args[0])
        sys.stderr.write('\n\n')
        sys.stderr.write(options.getSynopsis())
        sys.stderr.write('\n')
        sys.stderr.write(options.getUsage())
        raise SystemExit(1)

    certificates_path = FilePath(options['cert-directory'])
    cluster_cert = certificates_path.child(b"cluster.crt")
    user_cert = certificates_path.child(b"user.crt")
    user_key = certificates_path.child(b"user.key")
    client = FlockerClient(reactor, options['control-node'], REST_API_PORT,
                           cluster_cert, user_cert, user_key)
    return cleanup_cluster(client, options['timeout'])


@inlineCallbacks
def cleanup_cluster(client, timeout):
    """
    Delete all containers and datasets in the given cluster.

    :param FlockerClient client: The API client instance for the cluster.
    :param int timeout: A timeout in seconds for waiting until the deletions
        take effect.
    :returns: Deferred that fires when the clean up is complete.
    """
    containers = yield client.list_containers_configuration()
    results = []
    for container in containers:
        print "deleting container", container.name
        results.append(client.delete_container(container.name))
    yield gather_deferreds(results)

    def containers_deleted():
        d = client.list_containers_configuration()
        d.addCallback(lambda containers: not containers)
        return d

    yield loop_until(client._reactor, containers_deleted, repeat(1, timeout))

    datasets = yield client.list_datasets_configuration()
    results = []
    for dataset in datasets:
        print "deleting dataset with id", dataset.dataset_id
        results.append(client.delete_dataset(dataset.dataset_id))
    yield gather_deferreds(results)

    def datasets_deleted():
        d = client.list_datasets_configuration()
        d.addCallback(lambda datasets: not datasets.datasets)
        return d

    yield loop_until(client._reactor, datasets_deleted, repeat(1, timeout))
