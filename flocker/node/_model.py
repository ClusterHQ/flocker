# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_model -*-

"""
Record types for representing deployment models.
"""

from characteristic import attributes, Attribute
from zope.interface import Interface, implementer


@attributes(["repository", "tag"], defaults=dict(tag=u'latest'))
class DockerImage(object):
    """
    An image that can be used to run an application using Docker.

    :ivar unicode repository: eg ``u"hybridcluster/flocker"``
    :ivar unicode tag: eg ``u"release-14.0"``
    :ivar unicode full_name: A readonly property which combines the repository
        and tag in a format that can be passed to `docker run`.
    """

    @property
    def full_name(self):
        return "{repository}:{tag}".format(
            repository=self.repository, tag=self.tag)

    @classmethod
    def from_string(cls, input):
        """
        Given a Docker image name, return a :class:`DockerImage`.

        :param unicode input: A Docker image name in the format
            ``repository[:tag]``.

        :raises ValueError: If Docker image name is not in a valid format.

        :returns: A ``DockerImage`` instance.
        """
        kwargs = {}
        parts = input.rsplit(u':', 1)
        repository = parts[0]
        if not repository:
            raise ValueError("Docker image names must have format "
                             "'repository[:tag]'. Found '{image_name}'."
                             .format(image_name=input))
        kwargs['repository'] = repository
        if len(parts) == 2:
            kwargs['tag'] = parts[1]
        return cls(**kwargs)


@attributes(["name", "mountpoint", "maximum_size"],
            defaults=dict(maximum_size=None))
class AttachedVolume(object):
    """
    A volume attached to an application to be deployed.

    :ivar unicode name: A short, human-readable identifier for this
        volume. For now this is always the same as the name of the
        application it is attached to (see
        https://github.com/ClusterHQ/flocker/issues/49).

    :ivar FilePath mountpoint: The path within the container where this
        volume should be mounted.

    :ivar int maximum_size: The maximum size in bytes of this volume, or
        ``None`` for no limit.
    """

    @classmethod
    def from_unit(cls, unit):
        """
        Given a Docker ``Unit``, return a :class:`AttachedVolume`.

        :param Unit unit: A Docker ``Unit`` from which to create an
            ``AttachedVolume`` where the volume name will be the unit name
            and the mountpoint will be the unit's volume's container path.

        :returns: A set of ``AttachedVolume`` instances, or None if there
            is no volume within the supplied ``Unit`` instance.
        """
        volumes = set(unit.volumes)
        name = unit.name
        # XXX we only support one data volume per container at this time
        # https://github.com/ClusterHQ/flocker/issues/49
        try:
            volume = volumes.pop()
            return {cls(name=name, mountpoint=volume.container_path)}
        except KeyError:
            return None


class IRestartPolicy(Interface):
    """
    Restart policy for an application.
    """


@implementer(IRestartPolicy)
@attributes([], apply_immutable=True)
class RestartNever(object):
    """
    A restart policy that never restarts an application.
    """


@implementer(IRestartPolicy)
@attributes([], apply_immutable=True)
class RestartAlways(object):
    """
    A restart policy that always restarts an application.
    """
    def __init__(self):
        pass # Check model conditions


@implementer(IRestartPolicy)
@attributes(["maximum_retry_count"], apply_immutable=True)
class RestartOnFailre(object):
    """
    A restart policy that restarts an application when it fails.

    :ivar int maximum_retry_count: The number of times the application is
        allowed to fail, before the giving up.
    """



@attributes(["name", "image", "ports", "volume", "links", "environment",
             "memory_limit", "cpu_shares",
             Attribute("restart_policy", default=RestartNever())],
            defaults=dict(ports=frozenset(), volume=None,
                          links=frozenset(), environment=None,
                          memory_limit=None, cpu_shares=None))
class Application(object):
    """
    A single `application <http://12factor.net/>`_ to be deployed.

    XXX The links attribute defaults to ``None`` until we have a way to
    interrogate configured links.

    :ivar unicode name: A short, human-readable identifier for this
        application.  For example, ``u"site-example.com"`` or
        ``u"pgsql-payroll"``.

    :ivar DockerImage image: An image that can be used to run this
        containerized application.

    :ivar frozenset ports: A ``frozenset`` of ``Port`` instances that
        should be exposed to the outside world.

    :ivar volume: ``None`` if there is no volume, otherwise an
        ``AttachedVolume`` instance.

    :ivar frozenset links: A ``frozenset`` of ``Link``s that
        should be created between applications, or ``None`` if configuration
        information isn't available.

    :ivar frozenset environment: A ``frozenset`` of environment variables
        that should be exposed in the ``Application`` container, or ``None``
        if no environment variables are specified. A ``frozenset`` of
        variables contains a ``tuple`` series mapping (key, value).

    :ivar IRestartPolicy restart_policy: The restart policy for this
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

    :ivar frozenset applications: A ``frozenset`` of ``Application`` instances
        describing the applications which are to run on this ``Node``.
    """


@attributes(["nodes"])
class Deployment(object):
    """
    A ``Deployment`` describes the configuration of a number of applications on
    a number of cooperating nodes.  This might describe the real state of an
    existing deployment or be used to represent a desired future state.

    :ivar frozenset nodes: A ``frozenset`` containing ``Node`` instances
        describing the configuration of each cooperating node.
    """


@attributes(['internal_port', 'external_port'])
class Port(object):
    """
    A record representing the mapping between a port exposed internally by an
    application and the corresponding port exposed to the outside world.

    :ivar int internal_port: The port number exposed by the application.
    :ivar int external_port: The port number exposed to the outside world.
    """


@attributes(['local_port', 'remote_port', 'alias'])
class Link(object):
    """
    A record representing the mapping between a port exposed internally to
    an application, and the corresponding external port of a possibly remote
    application.

    :ivar int local_port: The port the local application expects to access.
        This is used to determine the environment variables to populate in the
        container.
    :ivar int remote_port: The port exposed externally by the remote
        application.
    :ivar unicode alias: Environment variable prefix to use for exposing
        connection information.
    """


@attributes(["volume", "hostname"])
class VolumeHandoff(object):
    """
    A record representing a volume handoff that needs to be performed from this
    node.

    See :cls:`flocker.volume.service.VolumeService.handoff`` for more details.

    :ivar AttachedVolume volume: The volume to hand off.
    :ivar bytes hostname: The hostname of the node to which the volume is
         meant to be handed off.
    """


@attributes(["going", "coming", "creating"])
class VolumeChanges(object):
    """
    ``VolumeChanges`` describes the volume-related changes necessary to change
    the current state to the desired state.

    :ivar frozenset going: The ``VolumeHandoff``\ s necessary to let other
        nodes take over hosting of any volume-having applications being moved
        away from a node.  These must be handed off.

    :ivar frozenset coming: The ``AttachedVolume``\ s necessary to let this
        node take over hosting of any volume-having applications being moved to
        this node.  These must be acquired.

    :ivar frozenset creating: The ``AttachedVolume``\ s necessary to let this
        node create any new volume-having applications meant to be hosted on
        this node.  These must be created.
    """


@attributes(["running", "not_running", "used_ports"],
            defaults={"used_ports": frozenset()})
class NodeState(object):
    """
    The current state of a node.

    :ivar running: A ``list`` of ``Application`` instances on this node
        that are currently running or starting up.
    :ivar not_running: A ``list`` of ``Application`` instances on this
        node that are currently shutting down or stopped.
    :ivar used_ports: A ``frozenset`` of ``int``\ s giving the TCP port numbers
        in use (by anything) on this node.
    """
