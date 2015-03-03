# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_model -*-

"""
Record types for representing deployment models.
"""

from characteristic import attributes, Attribute

from pyrsistent import (
    pmap, PRecord, field, PMap, PSet, pset,
    )

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


@attributes(["manifestation", "mountpoint"])
class AttachedVolume(object):
    """
    A volume attached to an application to be deployed.

    :ivar Manifestation manifestation: The ``Manifestation`` that is being
        attached as a volume. For now this is always from a ``Dataset``
        with the same as the name of the application it is attached to
        https://clusterhq.atlassian.net/browse/FLOC-49).

    :ivar FilePath mountpoint: The path within the container where this
        volume should be mounted.
    """
    @property
    def dataset(self):
        return self.manifestation.dataset


class IRestartPolicy(Interface):
    """
    Restart policy for an application.
    """


@implementer(IRestartPolicy)
@attributes([], apply_immutable=True,
            # https://github.com/hynek/characteristic/pull/22
            apply_with_init=False)
class RestartNever(object):
    """
    A restart policy that never restarts an application.
    """


@implementer(IRestartPolicy)
@attributes([], apply_immutable=True,
            # https://github.com/hynek/characteristic/pull/22
            apply_with_init=False)
class RestartAlways(object):
    """
    A restart policy that always restarts an application.
    """


@implementer(IRestartPolicy)
@attributes([Attribute("maximum_retry_count", default_value=None)],
            apply_immutable=True)
class RestartOnFailure(object):
    """
    A restart policy that restarts an application when it fails.

    :ivar int maximum_retry_count: The number of times the application is
        allowed to fail, before the giving up.
    """

    def __init__(self):
        """
        Check that ``maximum_retry_count`` is positive or None

        :raises ValueError: If maximum_retry_count is invalid.
        """
        if self.maximum_retry_count is not None:
            if not isinstance(self.maximum_retry_count, int):
                raise TypeError(
                    "maximum_retry_count must be an integer or None, "
                    "got %r" % (self.maximum_retry_count,))
            if self.maximum_retry_count < 1:
                raise ValueError(
                    "maximum_retry_count must be positive, "
                    "got %r" % (self.maximum_retry_count,))


@attributes(["name", "image",
             Attribute("ports", default_value=frozenset()),
             Attribute("volume", default_value=None),
             Attribute("links", default_value=frozenset()),
             Attribute("environment", default_value=None),
             Attribute("memory_limit", default_value=None),
             Attribute("cpu_shares", default_value=None),
             Attribute("restart_policy", default_value=RestartNever())])
class Application(object):
    """
    A single `application <http://12factor.net/>`_ to be deployed.

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


class Dataset(PRecord):
    """
    The filesystem data for a particular application.

    At some point we'll want a way of reserving metadata for ourselves.

    :ivar dataset_id: A unique identifier, as ``unicode``. May also be ``None``
        if this is coming out of human-supplied configuration, in which
        case it will need to be looked up from actual state for existing
        datasets, or a new one generated if a new dataset will need tbe
        created.

    :ivar bool deleted: If ``True``, this dataset has been deleted and its
        data is unavailable, or will soon become unavailable.

    :ivar PMap metadata: Mapping between ``unicode`` keys and
        corresponding values. Typically there will be a ``"name"`` key whose
        value is a a human-readable name, e.g. ``"main-postgres"``.

    :ivar int maximum_size: The maximum size in bytes of this dataset, or
        ``None`` if there is no specified limit.
    """
    dataset_id = field(mandatory=True, type=unicode, factory=unicode)
    deleted = field(mandatory=True, initial=False, type=bool)
    maximum_size = field(mandatory=True, initial=None)
    metadata = field(mandatory=True, type=PMap, factory=pmap, initial=pmap())


class Manifestation(PRecord):
    """
    A dataset that is mounted on a node.

    :ivar Dataset dataset: The dataset being mounted.

    :ivar bool primary: If true, this is a primary, otherwise it is a replica.
    """
    dataset = field(mandatory=True, type=Dataset)
    primary = field(mandatory=True, type=bool)

    @property
    def dataset_id(self):
        """
        :return unicode: The dataset ID of the dataset.
        """
        return self.dataset.dataset_id


class Node(PRecord):
    """
    A single node on which applications will be managed (deployed,
    reconfigured, destroyed, etc).

    Manifestations attached to applications must also be present in the
    ``manifestations`` attribute.

    :ivar unicode hostname: The hostname of the node.  This must be a
        resolveable name so that Flocker can connect to the node.  This may be
        a literal IP address instead of a proper hostname.

    :ivar frozenset applications: A ``frozenset`` of ``Application`` instances
        describing the applications which are to run on this ``Node``.

    :ivar PMap manifestations: Mapping between dataset IDs and
        corresponding ``Manifestation`` instances that are present on the
        node. Includes both those attached as volumes to any applications,
        and those that are unattached.
    """
    def __invariant__(self):
        manifestations = self.manifestations.values()
        for app in self.applications:
            if not isinstance(app, Application):
                return (False, '%r must be Appplication' % (app,))
            if app.volume is not None:
                if app.volume.manifestation not in manifestations:
                    return (False, '%r manifestation is not on node' % (app,))
        for key, value in self.manifestations.items():
            if key != value.dataset_id:
                return (False, '%r is not correct key for %r' % (key, value))
        return (True, "")

    hostname = field(type=unicode, factory=unicode, mandatory=True)
    applications = field(type=PSet, initial=pset(), factory=pset,
                         mandatory=True)
    manifestations = field(type=PMap, initial=pmap(), factory=pmap,
                           mandatory=True)


@attributes(["nodes"])
class Deployment(object):
    """
    A ``Deployment`` describes the configuration of a number of applications on
    a number of cooperating nodes.  This might describe the real state of an
    existing deployment or be used to represent a desired future state.

    :ivar frozenset nodes: A ``frozenset`` containing ``Node`` instances
        describing the configuration of each cooperating node.
    """
    def applications(self):
        """
        Return all applications in all nodes.

        :return: Iterable returning all applications.
        """
        for node in self.nodes:
            for application in node.applications:
                yield application

    def update_node(self, node):
        """
        Create new ``Deployment`` based on this one which replaces existing
        ``Node`` with updated version, or just adds given ``Node`` if no
        existing ones have matching hostname.

        :param Node node: An update for ``Node`` with same hostname in
             this ``Deployment``.

        :return Deployment: Updated with new ``Node``.
        """
        return Deployment(nodes=frozenset(
            list(n for n in self.nodes if n.hostname != node.hostname) +
            [node]))


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


@attributes(["dataset", "hostname"])
class DatasetHandoff(object):
    """
    A record representing a dataset handoff that needs to be performed
    from this node.

    See :cls:`flocker.volume.service.VolumeService.handoff`` for more details.

    :ivar Dataset dataset: The dataset to hand off.
    :ivar bytes hostname: The hostname of the node to which the volume is
         meant to be handed off.
    """


@attributes(["going", "coming", "creating", "resizing"])
class DatasetChanges(object):
    """
    The dataset-related changes necessary to change the current state to
    the desired state.

    :ivar frozenset going: The ``DatasetHandoff``\ s necessary to let
        other nodes take over hosting datasets being moved away from a
        node.  These must be handed off.

    :ivar frozenset coming: The ``Dataset``\ s necessary to let this
        node take over hosting of any datasets being moved to
        this node.  These must be acquired.

    :ivar frozenset creating: The ``Dataset``\ s necessary to let this
        node create any new datasets meant to be hosted on
        this node.  These must be created.

    :ivar frozenset resizing: The ``Dataset``\ s necessary to let this
        node resize any existing datasets that are desired somewhere on
        the cluster and locally exist with a different maximum_size to the
        desired maximum_size. These must be resized.
    """


class NodeState(PRecord):
    """
    The current state of a node.

    :ivar unicode hostname: The hostname of the node.
    :ivar running: A ``PSet`` of ``Application`` instances on this node
        that are currently running or starting up.
    :ivar not_running: A ``PSet`` of ``Application`` instances on this
        node that are currently shutting down or stopped.
    :ivar used_ports: A ``PSet`` of ``int``\ s giving the TCP port numbers
        in use (by anything) on this node.
    :ivar PSet manifestations: All ``Manifestation`` instances that
        are present on the node.
    """
    hostname = field(type=unicode, factory=unicode, mandatory=True)
    used_ports = field(type=PSet, initial=pset(), factory=pset,
                       mandatory=True)
    running = field(type=PSet, initial=pset(), factory=pset,
                    mandatory=True)
    not_running = field(type=PSet, initial=pset(), factory=pset,
                        mandatory=True)
    manifestations = field(type=PSet, initial=pset(), factory=pset,
                           mandatory=True)

    def to_node(self):
        """
        Convert into a ``Node`` instance.

        :return Node: Equivalent ``Node`` object.
        """
        return Node(hostname=self.hostname,
                    manifestations={m.dataset_id: m
                                    for m in self.manifestations},
                    applications=self.running | self.not_running)
