# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_model -*-

"""
Record types for representing deployment models.

There are different categories of classes:

1. Those that involve information that can be both in configuration and state.
   This includes ``Deployment`` and all classes on it.
   (Metadata should really be configuration only, but that hasn't been
   fixed yet on the model level.)
2. State-specific classes, currently ``NodeState``.
3. Configuration-specific classes, none implemented yet.
"""

from characteristic import attributes

from twisted.python.filepath import FilePath
from pyrsistent import (
    pmap, PRecord, field, PMap, CheckedPSet, CheckedPMap,
    )

from zope.interface import Interface, implementer


def pset_field(klass):
    """
    Create checked ``PSet`` field that can serialize recursively.

    :return: A ``field`` containing a ``CheckedPSet`` of the given type.
    """
    class TheSet(CheckedPSet):
        __type__ = klass
    TheSet.__name__ = klass.__name__ + "PSet"

    return field(type=TheSet, factory=TheSet.create, mandatory=True,
                 initial=TheSet())


class DockerImage(PRecord):
    """
    An image that can be used to run an application using Docker.

    :ivar unicode repository: eg ``u"hybridcluster/flocker"``
    :ivar unicode tag: eg ``u"release-14.0"``
    :ivar unicode full_name: A readonly property which combines the repository
        and tag in a format that can be passed to `docker run`.
    """
    repository = field(mandatory=True)
    tag = field(mandatory=True, initial=u"latest")

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


class Port(PRecord):
    """
    A record representing the mapping between a port exposed internally by an
    application and the corresponding port exposed to the outside world.

    :ivar int internal_port: The port number exposed by the application.
    :ivar int external_port: The port number exposed to the outside world.
    """
    internal_port = field(mandatory=True, type=int)
    external_port = field(mandatory=True, type=int)


class Link(PRecord):
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
    local_port = field(mandatory=True, type=int)
    remote_port = field(mandatory=True, type=int)
    alias = field(mandatory=True)


class IRestartPolicy(Interface):
    """
    Restart policy for an application.
    """


@implementer(IRestartPolicy)
class RestartNever(PRecord):
    """
    A restart policy that never restarts an application.
    """


@implementer(IRestartPolicy)
class RestartAlways(PRecord):
    """
    A restart policy that always restarts an application.
    """


@implementer(IRestartPolicy)
class RestartOnFailure(PRecord):
    """
    A restart policy that restarts an application when it fails.

    :ivar maximum_retry_count: The number of times the application is
        allowed to fail before giving up, or ``None`` if there is no
        maximum.
    """
    maximum_retry_count = field(mandatory=True, initial=None)

    def __invariant__(self):
        """
        Check that ``maximum_retry_count`` is positive or None

        :raises ValueError: If maximum_retry_count is invalid.
        """
        if self.maximum_retry_count is not None:
            if not isinstance(self.maximum_retry_count, int):
                return (False,
                        "maximum_retry_count must be an integer or None, "
                        "got %r" % (self.maximum_retry_count,))
            if self.maximum_retry_count < 1:
                return (False,
                        "maximum_retry_count must be positive, "
                        "got %r" % (self.maximum_retry_count,))
        return (True, "")


class Application(PRecord):
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

    :ivar PSet environment: A ``frozenset`` of environment variables
        that should be exposed in the ``Application`` container, or ``None``
        if no environment variables are specified. A ``frozenset`` of
        variables contains a ``tuple`` series mapping (key, value).

    :ivar IRestartPolicy restart_policy: The restart policy for this
        application.
    """
    name = field(mandatory=True)
    image = field(mandatory=True, type=DockerImage)
    ports = pset_field(Port)
    volume = field(mandatory=True, initial=None)
    links = pset_field(Link)
    memory_limit = field(mandatory=True, initial=None)
    cpu_shares = field(mandatory=True, initial=None)
    restart_policy = field(mandatory=True, initial=RestartNever())
    environment = field(mandatory=True, initial=pmap(), factory=pmap,
                        type=PMap)


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
    metadata = field(mandatory=True, type=PMap, factory=pmap, initial=pmap(),
                     serializer=lambda f, d: dict(d))


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


class AttachedVolume(PRecord):
    """
    A volume attached to an application to be deployed.

    :ivar Manifestation manifestation: The ``Manifestation`` that is being
        attached as a volume. For now this is always from a ``Dataset``
        with the same as the name of the application it is attached to
        https://clusterhq.atlassian.net/browse/FLOC-49).

    :ivar FilePath mountpoint: The path within the container where this
        volume should be mounted.
    """
    manifestation = field(mandatory=True, type=Manifestation)
    mountpoint = field(mandatory=True, type=FilePath)

    @property
    def dataset(self):
        return self.manifestation.dataset


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
            if app.volume is not None:
                if app.volume.manifestation not in manifestations:
                    return (False, '%r manifestation is not on node' % (app,))
        for key, value in self.manifestations.items():
            if key != value.dataset_id:
                return (False, '%r is not correct key for %r' % (key, value))
        return (True, "")

    hostname = field(type=unicode, factory=unicode, mandatory=True)
    applications = pset_field(Application)
    manifestations = field(type=PMap, initial=pmap(), factory=pmap,
                           mandatory=True)


class Deployment(PRecord):
    """
    A ``Deployment`` describes the configuration of a number of applications on
    a number of cooperating nodes.  This might describe the real state of an
    existing deployment or be used to represent a desired future state.

    :ivar PSet nodes: A set containing ``Node`` instances
        describing the configuration of each cooperating node.
    """
    nodes = pset_field(Node)

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


@attributes(["going", "coming", "creating", "resizing", "deleting"])
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

    :ivar frozenset deleting: The ``Dataset``\ s that should be deleted.
    """


class _PathMap(CheckedPMap):
    """
    A mapping between dataset IDs and the paths where they are mounted.

    See https://github.com/tobgu/pyrsistent/issues/26 for more succinct
    idiom combining this with ``field()``.
    """
    __key_type__ = unicode
    __value_type__ = FilePath


class NodeState(PRecord):
    """
    The current state of a node.

    This includes information that is state-specific and thus does not
    belong in ``Node``, the latter being shared between both state and
    configuration models.

    :ivar unicode hostname: The hostname of the node.
    :ivar running: A ``PSet`` of ``Application`` instances on this node
        that are currently running or starting up.
    :ivar not_running: A ``PSet`` of ``Application`` instances on this
        node that are currently shutting down or stopped.
    :ivar used_ports: A ``PSet`` of ``int``\ s giving the TCP port numbers
        in use (by anything) on this node.
    :ivar PSet manifestations: All ``Manifestation`` instances that
        are present on the node.
    :ivar PMap paths: The filesystem paths of the manifestations on this
        node. Maps ``dataset_id`` to a ``FilePath``.
    """
    hostname = field(type=unicode, factory=unicode, mandatory=True)
    used_ports = pset_field(int)

    # XXX: Consider an issue for a new `DatasetState` so that dataset
    # convergence agents don't have to worry about running and not_running
    # applications.
    # See https://github.com/ClusterHQ/flocker/pull/1206#issue-60483012
    running = pset_field(Application)
    not_running = pset_field(Application)
    manifestations = pset_field(Manifestation)
    paths = field(type=_PathMap, initial=_PathMap(), factory=_PathMap.create,
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


# Classes that can be serialized to disk or sent over the network:
SERIALIZABLE_CLASSES = [
    Deployment, Node, DockerImage, Port, Link, RestartNever, RestartAlways,
    RestartOnFailure, Application, Dataset, Manifestation, AttachedVolume,
    NodeState,
]
