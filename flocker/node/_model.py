# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_model -*-

"""
Record types for representing deployment models.
"""

from characteristic import attributes


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


@attributes(["name", "mountpoint"])
class AttachedVolume(object):
    """
    A volume attached to an application to be deployed.

    :ivar unicode name: A short, human-readable identifier for this
        volume. For now this is always the same as the name of the
        application it is attached to (see
        https://github.com/ClusterHQ/flocker/issues/49).

    :ivar FilePath mountpoint: The path within the container where this
        volume should be mounted, or ``None`` if unknown
        (see https://github.com/ClusterHQ/flocker/issues/289).
    """


@attributes(["name", "image", "ports", "volume", "links", "environment"],
            defaults=dict(image=None, ports=frozenset(), volume=None,
                          links=None, environment=None))
class Application(object):
    """
    A single `application <http://12factor.net/>`_ to be deployed.

    XXX: The image attribute defaults to ``None`` until we have a way to
    interrogate geard for the docker images associated with its
    containers. See https://github.com/ClusterHQ/flocker/issues/207

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
