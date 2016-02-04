import sys

from eliot import FileDestination, add_destination

from twisted.internet.defer import DeferredList, inlineCallbacks, succeed
from twisted.python.usage import UsageError

from .acceptance import (
    eliot_output,
    make_managed_nodes,
    RunOptions
)


def main(reactor, args, base_path, top_level):
    """
    :param reactor: Reactor to use.
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the Flocker repository.
    """
    add_destination(eliot_output)
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
        options['distribution']
    )
    node_ips = [node.address for node in existing_nodes]
    options.runner.gather_managed_nodes(reactor, node_ips)
    options.runner.stop_cluster(reactor)
    succeed('OK')
