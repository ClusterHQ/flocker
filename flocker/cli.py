# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from characteristic import attributes

from yaml import safe_load


@attributes(["mount_path"])
class Volume(object):
    """
    A single filesystem volume to be associated with an application.

    :ivar FilePath mount_path: The absolute path at which the volume will be
        mounted onto the application image filesystem.
    """


@attributes(["repository", "tag"])
class DockerImage(object):
    """
    An image that can be used to run an application using Docker.

    :ivar unicode repository: eg ``u"hybridcluster/flocker"``
    :ivar unicode tag: eg ``u"release-14.0"``
    """


@attributes(["name", "image", "volume"])
class Application(object):
    """
    A single `application <http://12factor.net/>`_ to be deployed.

    :ivar unicode name: A short, human-readable identifier for this
        application.  For example, ``u"site-example.com"`` or
        ``u"pgsql-payroll"``.

    :ivar DockerImage image: An image that can be used to run this containerized
        application.

    :ivar Volume volume: A volume which will always be made available with this
        application.
    """


@attributes(["hostname", "applications"])
class Node(object):
    """
    A single node on which applications will be managed (deployed,
    reconfigured, destroyed, etc).

    :ivar unicode hostname: The hostname of the node.  This must be a
        resolveable name so that Flocker can connect to the node.  This may be
        a literal IP address instead of a proper hostname.

    :ivar set applications: A ``set`` of ``Application`` instances describing
        the applications which are to run on this ``Node``.
    """


@attributes(["nodes"])
class Deployment(object):
    """
    A ``Deployment`` describes the configuration of a number of applications on
    a number of cooperating nodes.  This might describe the real state of an
    existing deployment or be used to represent a desired future state.

    :ivar set nodes: A ``set`` containing ``Node`` instances describing the
        configuration of each cooperating node.
    """


def load_configuration(application_config_path, deployment_config_path):
    # {"version": 1,
    #  "applications": {
    #      "mysql-hybridcluster": {"image": "hybridlogic/mysql5.9:latest", "volume": "/var/run/mysql"}
    #  }
    # }
    application_config = safe_load(application_config_path)
    assert application_config[u"version"] == 1
    applications = dict([
        (name, Application(
                    name,
                    DockerImage(*config[u"image"].rsplit(u":", 1)),
                    Volume(config[u"volume"])))
        for (name, config)
        in application_config[u"applications"].items()
        ])


    #
    # {"version": 1,
    #  "nodes": {
    #      "node1": ["mysql-hybridcluster"],
    #      "node2": ["site-hybridcluster.com"]
    #  }
    # }
    #
    deployment_config = safe_load(deployment_config_path.getContent())
    assert deployment_config[u"version"] == 1

    nodes = {
        Node(hostname, [applications[app_name] for app_name in app_names])
        for (hostname, app_names)
        in deployment_config[u"nodes"].items()
        }

    return Deployment(nodes)


def discover_configuration(hostnames):
    """
    :param set hostnames: A ``set`` of ``unicode`` hostnames identifying the
        nodes on which relevant configuration may be found.

    :return: A ``Deployment`` instance describing the deployment state across
        all the given nodes.
    """
    nodes = {
        Node(hostname, set()) for hostname in hostnames}

    for node in nodes:
        node.applications.update(
            discover_node_configuration(node.hostname))

    return Deployment(nodes)


def discover_node_configuration(hostname):
    volumes = flocker_volume_list()
    containers = docker_ps_list()
    units = geard_list()
    return [
        Application(name, image, volume)
        for (name, image, volume)
        in magically_correlate(volumes, containers, units)
        ]



def deploy(actual_configuration, desired_configuration):
    """
    Update a deployment.

    Stop any running applications which are not described by the given
    configuration.  Start any applications which are described by it but are
    not yet running.  Move any applications (with their data volumes) that are
    running on a different node than specified by the configuration.

    :param desired_configuration: A ``set`` of ``Deployment`` instances
        describing the complete configuration of applications on a
        participating collection of nodes.
    """
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
    deploy(actual_configuration, desired_configuration)
