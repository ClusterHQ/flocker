from sys import stdin

from yaml import safe_load

from characteristic import attributes

from ._model import Application
from ._config import model_from_configuration
from ._inspect import flocker_volume_list, docker_ps_list, geard_list

from ..volume import push_volume, wait_for_volume


@attributes(["coming", "going"])
class Moves(object):
    pass


def magically_correlate(volumes, containers, units):
    pass


def is_this_node(node):
    pass


def discover_node_configuration():
    volumes = flocker_volume_list()
    containers = docker_ps_list()
    units = geard_list()
    return dict([
            (name, Application(name, image, volume))
            for (name, image, volume)
            in magically_correlate(volumes, containers, units)
            ])


def start_container(app):
    pass


def stop_container(app):
    pass


def deploy(desired_configuration):
    """
    :param Deployment desired_configuration:
    """
    #
    # XXX What if someone does another deploy in parallel?  Need to lock the
    # node so only one deployment can happen at a time.
    #
    applications = discover_node_configuration()

    # Find any applications that have moved from this node to another node or
    # from another node to this node.
    moves = find_moves(applications, desired_configuration)

    # Push the volumes for all of those applications to the node the
    # application is moving to.
    for (app, node) in moves.going:
        push_volume(app.volume, node)

    # Wait for all volumes that will need to be pushed to this node.
    for app in moves.coming:
        wait_for_volume(app.volume)

    # Stop all containers that are being moved or just eliminated.
    for (app, node) in moves.going:
        stop_container(app)

    # Start all containers that have been moved here or are brand new.
    for app in moves.coming:
        start_container(app)


def find_moves(applications, desired_configuration):
    """
    Figure out which applications are moving between nodes.
    """
    coming = []
    going = []
    app_to_node = {}
    for node in desired_configuration.nodes:
        for app in node.applications:
            app_to_node[app.name] = node

    for app in applications:
        node = app_to_node[app.name]
        if not is_this_node(node):
            going.append((app, node))

    return Moves(coming=coming, going=going)


def main():
    configuration = safe_load(stdin.read())
    application_config = configuration[u"application"]
    deployment_config = configuration[u"deployment"]
    desired_configuration = model_from_configuration(
        application_config, deployment_config)

    deploy(desired_configuration)
