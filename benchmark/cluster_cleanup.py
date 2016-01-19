# Copyright ClusterHQ Inc.  See LICENSE file for details.

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
         "The address of the cluster's control node."],
        ['cert-directory', None, None,
         "The directory containing the cluster certificates."],
        ['wait', None, None,
         "The timeout in seconds for waiting until the operation is complete. "
         "No waiting is done by default."]
    ]

    def postOptions(self):
        if not self['control-node']:
            raise UsageError("Control node address must be provided.")
        if not self['cert-directory']:
            raise UsageError("Certificates directory must be provided.")
        if self['wait'] is not None:
            try:
                self['wait'] = int(self['wait'])
            except ValueError:
                raise UsageError("The wait timeout must be an integer.")


def main(reactor, args):
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
    return cleanup_cluster(client, options['wait'])


@inlineCallbacks
def cleanup_cluster(client, timeout=None):
    """
    Delete all containers and datasets in the given cluster.

    :param FlockerClient client: The API client instance for the cluster.
    :param timeout: A timeout in seconds for waiting until the deletions
        take effect if not ``None``, otherwise there is no waiting.
    :type timeout: int or None
    :returns: Deferred that fires when the clean up is complete if
        :param:`timeout` is not None, otherwise the Deferred fires
        when the deletion requests are aknowledged.
    """
    containers_configuration = yield client.list_containers_configuration()
    results = []
    for container in containers_configuration:
        print "deleting container", container.name
        results.append(client.delete_container(container.name))
    yield gather_deferreds(results)

    datasets_configuration = yield client.list_datasets_configuration()
    results = []
    for dataset in datasets_configuration:
        print "deleting dataset with id", dataset.dataset_id
        results.append(client.delete_dataset(dataset.dataset_id))
    yield gather_deferreds(results)

    if timeout is not None:
        print "waiting for all containers to get deleted"
        yield loop_until(
            client._reactor,
            lambda: client.list_containers_state().addCallback(
                lambda containers: not containers
            ),
            repeat(1, timeout)
        )
        print "waiting for all datasets to get deleted"
        yield loop_until(
            client._reactor,
            lambda: client.list_datasets_state().addCallback(
                lambda datasets: not datasets
            ),
            repeat(1, timeout)
        )
