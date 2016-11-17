# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Provision new nodes and add them to an existing cluster.
"""

import sys

from eliot import FileDestination

from twisted.internet.defer import DeferredList, inlineCallbacks
from twisted.python.usage import UsageError
from twisted.python.filepath import FilePath

from flocker.provision._ca import Certificates
from flocker.provision._common import Cluster

from .acceptance import (
    capture_journal,
    capture_upstart,
    configure_eliot_logging_for_acceptance,
    get_default_volume_size,
    make_managed_nodes,
    save_backend_configuration,
)
from .cluster_setup import (
    RunOptions as SetupOptions,
    make_client,
    save_environment,
    save_managed_config,
    wait_for_nodes,
)


class RunOptions(SetupOptions):
    optParameters = [
        ['purpose', None, 'testing',
         "Purpose of the cluster recorded in its metadata where possible."],
        ['tag', None, None,
         "Tag used in names of the existing cluster nodes."],
        ['control-node', None, None,
         "The address of the cluster's control node."],
        ['cert-directory', None, None,
         "Directory with the cluster certificates. "],
        ['number-of-nodes', None, 1,
         "Number of new nodes to create.", int],
        ['starting-index', None, None,
         "Starting index to use in names of new nodes.", int],
    ]

    synopsis = 'Usage: add-cluster-nodes [options]'

    def __init__(self, top_level):
        """
        :param FilePath top_level: The top-level of the Flocker repository.
        """
        super(RunOptions, self).__init__(top_level)
        self._remove_options(['no-keep'])

    def _remove_options(self, to_remove):
        """
        Remove the given options that are defined in the parent classes.

        :param to_remove: The options to rmeove.
        :type to_remove: list of str

        .. note::
            Option names should be given as is,
            parameter names should have '=' suffix.
        """
        self.longOpt = [opt for opt in self.longOpt if opt not in to_remove]

    def postOptions(self):
        if not self['control-node']:
            raise UsageError("Control node address must be provided.")
        if self.get('cert-directory') is None:
            raise UsageError("Certificate directory must be set.")
        if self.get('tag') is None:
            raise UsageError("Tag must be specified.")

        # This is run last as it creates the actual "runner" object
        # based on the provided parameters.
        super(RunOptions, self).postOptions()

    def _check_cert_directory(self):
        cert_path = FilePath(self['cert-directory'])
        self['cert-directory'] = cert_path
        if not cert_path.exists():
            raise UsageError("{} does not exist".format(cert_path.path))
        if not cert_path.isdir():
            raise UsageError("{} is not a directory".format(cert_path.path))


@inlineCallbacks
def main(reactor, args, base_path, top_level):
    """
    :param reactor: Reactor to use.
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the Flocker repository.
    """
    configure_eliot_logging_for_acceptance()
    options = RunOptions(top_level=top_level)
    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        sys.stderr.write("\n")
        sys.stderr.write(str(options))
        raise SystemExit(1)

    # Existing nodes must be described in a managed section
    # of the configuration.
    existing_nodes = make_managed_nodes(
        options['config']['managed']['addresses'],
        options['distribution'],
    )
    # The following code assumes that one of the managed nodes
    # is both a control node and an agent node.
    [control_node] = [
        node for node in existing_nodes
        if node.address == options['control-node']
    ]
    dataset_backend_config_file = save_backend_configuration(
        options.dataset_backend(),
        options.dataset_backend_configuration(),
    )
    cluster = Cluster(
        all_nodes=list(existing_nodes),
        control_node=control_node,
        agent_nodes=list(existing_nodes),
        dataset_backend=options.dataset_backend(),
        default_volume_size=get_default_volume_size(
            options.dataset_backend_configuration()
        ),
        certificates=Certificates(options['cert-directory']),
        dataset_backend_config_file=dataset_backend_config_file,
    )

    flocker_client = make_client(reactor, cluster)
    existing_count = len(existing_nodes)
    yield wait_for_nodes(reactor, flocker_client, existing_count)
    if options['starting-index'] is None:
        options['starting-index'] = existing_count

    print(
        "Adding {} node(s) to the cluster of {} nodes "
        "starting at index {}".format(
            options['number-of-nodes'],
            existing_count,
            options['starting-index'],
        )
    )

    runner = options.runner
    cleanup_id = reactor.addSystemEventTrigger('before', 'shutdown',
                                               runner.stop_cluster, reactor)

    from flocker.common.script import eliot_logging_service
    log_writer = eliot_logging_service(
        destination=FileDestination(
            file=open("%s.log" % (base_path.basename(),), "a")
        ),
        reactor=reactor,
        capture_stdout=False)
    log_writer.startService()
    reactor.addSystemEventTrigger(
        'before', 'shutdown', log_writer.stopService)

    control_node = options['control-node']
    if options['distribution'] in ('centos-7',):
        remote_logs_file = open("remote_logs.log", "a")
        capture_journal(reactor, control_node, remote_logs_file)
    elif options['distribution'] in ('ubuntu-14.04',):
        remote_logs_file = open("remote_logs.log", "a")
        capture_upstart(reactor, control_node, remote_logs_file)

    yield runner.ensure_keys(reactor)

    deferreds = runner.extend_cluster(
        reactor,
        cluster,
        options['number-of-nodes'],
        options['tag'],
        options['starting-index'],
    )
    results = yield DeferredList(deferreds)

    failed_count = 0
    for (success, _) in results:
        if not success:
            failed_count += 1
    if failed_count:
        print "Failed to create {} nodes, see logs.".format(failed_count)

    yield wait_for_nodes(
        reactor,
        flocker_client,
        len(cluster.agent_nodes),
    )

    save_managed_config(options['cert-directory'], options['config'], cluster)
    save_environment(
        options['cert-directory'], cluster, options.package_source()
    )
    reactor.removeSystemEventTrigger(cleanup_id)
