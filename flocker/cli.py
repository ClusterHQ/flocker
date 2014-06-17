# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.internet.defer import gatherResults

def deploy(desired_configuration):
    """
    Update a deployment.

    Stop any running applications which are not described by the given
    configuration.  Start any applications which are described by it but are
    not yet running.  Move any applications (with their data volumes) that are
    running on a different node than specified by the configuration.

    :param desired_configuration: A ``set`` of ``Deployment`` instances
        describing the complete configuration of applications on a
        participating collection of nodes.  This is the desired configuration
        which the resulting changes will achieve.
    """
    _node_directed_deploy(desired_configuration)


def _node_directed_deploy(desired_configuration):
    """
    A deployment strategy which delegates all of the hard work to the
    individual nodes.

    Specifically, contact each node mentioned in ``desired_configuration`` and
    tell it what the cluster-wide desired configuration is.  Let each node
    figure out what changes need to be made on that node and then make them
    itself.
    """
    return gatherResults(
        _node_directed_single_deploy(node, desired_configuration)
        for node in desired_configuration)


def _node_directed_single_deploy(node, desired_configuration):
    """
    Contact the specified node and tell it to change its configuration to match
    ``desired_configuration``.

    :param Node: node:
    """
    endpoint = ProcessEndpoint(reactor, b"ssh", b"flocker-node", b"--deploy")

    stops = determine_stops(actual_configuration, desired_configuration)
    moves = determine_moves(actual_configuration, desired_configuration)
    starts = determine_starts(actual_configuration, desired_configuration)

    stop_containers(stops)
    move_containers(moves)
    start_containers(starts)


def move_containers(moves):
    # Push volumes that need to move
    # Stop containers that need to move
    # Re-push volumes that need to move
    # Start containers that have moved
    # Mumble mumble networks
    pass


def main(application_config_path, deployment_config_path):
    desired_configuration = load_configuration(
        application_config_path, deployment_config_path)
    actual_configuration = discover_configuration(
        {node.hostname for node in desired_configuration.nodes})
    changes = determine_changes(actual_configuration, desired_configuration)
    deploy(changes)
