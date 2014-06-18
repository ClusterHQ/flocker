from sys import stdin

from yaml import safe_load

from characteristic import attributes

from ._model import Application
from ._config import model_from_configuration
from ._inspect import flocker_volume_list, geard_list

from ..volume import push_volume, wait_for_volume, handoff_volume


@attributes(["coming", "going"])
class Moves(object):
    pass


def magically_correlate(volumes, containers, units):
    pass


def is_this_node(node):
    pass


def iterapps(configuration):
    for node in configuration.nodes:
        for app in node.applications:
            yield (node, app)


def discover_node_configuration():
    containers = geard_list()
    volumes = flocker_volume_list()

    return dict([
            (name, Application(name, image, volume))
            for (name, image, volume)
            in magically_correlate(volumes, containers)
            ])


def start_container(app):
    # do a thing with gear to start a container
    # specify localhost-only versions of links to gear
    # set up inter-node links with flocker.route
    pass


def stop_container(app):
    # stop the container
    # clean up the inter-node links
    pass


def external_proxying(configuration):
    for (node, app) in iterapps(configuration):
        for route in app.routes:
            # tear down any existing irrelevant proxies.
            #
            # XXX this destroys more than necessary since not all apps are
            # necessarily moving.
            route.destroy()

            # create new ones for the new (or maybe unchanged) configuration
            route.create_for(node, app)


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

    # Stop all containers that are being moved or just eliminated.
    for (app, node) in moves.going:
        stop_container(app)

    # Push the volumes for all of those applications to the node the
    # application is moving to.
    for (app, node) in moves.going:
        handoff_volume(app.volume, node)

    # Wait for all volumes that will need to be pushed to this node.
    for app in moves.coming:
        wait_for_volume(app.volume)

    # Start all containers that have been moved here or are brand new.
    for app in moves.coming:
        start_container(app)

    # Set up external proxying
    external_proxying(desired_configuration)


def find_moves(applications, desired_configuration):
    """
    Figure out which applications are moving between nodes.

    :param dict applications: The applications that are currently running on
        this node.  A mapping from names to ``Application`` instances.
    """
    coming = []
    going = []
    app_to_node = {}
    for (node, app) in iterapps(desired_configuration):
        app_to_node[app.name] = node

    # Inspect all the running applications
    for app in applications:
        node = app_to_node[app.name]
        if not is_this_node(node):
            going.append((app, node))

    # Inspect all the configured applications - including applications that
    # possibly should be running here.
    for (node, app) in iterapps(desired_configuration):
        if is_this_node(node) and app.name not in applications:
            coming.append(app)

    return Moves(coming=coming, going=going)
