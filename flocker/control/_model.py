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

from uuid import UUID
from warnings import warn
from hashlib import md5
from datetime import datetime

from characteristic import attributes
from twisted.python.filepath import FilePath

from pyrsistent import (
    pmap, PRecord, field, PMap, CheckedPSet, CheckedPMap, discard,
    optional as optional_type, CheckedPVector,
    )

from zope.interface import Interface, implementer


def _sequence_field(checked_class, suffix, item_type, optional, initial):
    """
    Create checked field for either ``PSet`` or ``PVector``.

    :param checked_class: ``CheckedPSet`` or ``CheckedPVector``.
    :param suffix: Suffix for new type name.
    :param item_type: The required type for the items in the set.
    :param bool optional: If true, ``None`` can be used as a value for
        this field.
    :param initial: Initial value to pass to factory.

    :return: A ``field`` containing a checked class.
    """
    class TheType(checked_class):
        __type__ = item_type
    TheType.__name__ = item_type.__name__.capitalize() + suffix

    if optional:
        def factory(argument):
            if argument is None:
                return None
            else:
                return TheType(argument)
    else:
        factory = TheType
    return field(type=optional_type(TheType) if optional else TheType,
                 factory=factory, mandatory=True,
                 initial=factory(initial))


def pset_field(item_type, optional=False, initial=()):
    """
    Create checked ``PSet`` field.

    :param item_type: The required type for the items in the set.
    :param bool optional: If true, ``None`` can be used as a value for
        this field.
    :param initial: Initial value to pass to factory if no value is given
        for the field.

    :return: A ``field`` containing a ``CheckedPSet`` of the given type.
    """
    return _sequence_field(CheckedPSet, "PSet", item_type, optional,
                           initial)


def pvector_field(item_type, optional=False, initial=()):
    """
    Create checked ``PVector`` field.

    :param item_type: The required type for the items in the vector.
    :param bool optional: If true, ``None`` can be used as a value for
        this field.
    :param initial: Initial value to pass to factory if no value is given
        for the field.

    :return: A ``field`` containing a ``CheckedPVector`` of the given type.
    """
    return _sequence_field(CheckedPVector, "PVector", item_type, optional,
                           initial)


_valid = lambda item: (True, "")


_UNDEFINED = object()


def pmap_field(
    key_type, value_type, optional=False, invariant=_valid,
    initial=_UNDEFINED
):
    """
    Create a checked ``PMap`` field.

    :param key: The required type for the keys of the map.
    :param value: The required type for the values of the map.
    :param bool optional: If true, ``None`` can be used as a value for this
        field.
    :param invariant: Pass-through to ``field``.
    :param initial: An initial value for the field.  This will first be coerced
        using the field's factory.  If not given, the initial value is an empty
        map.

    :return: A ``field`` containing a ``CheckedPMap``.
    """
    class TheMap(CheckedPMap):
        __key_type__ = key_type
        __value_type__ = value_type
    TheMap.__name__ = (key_type.__name__.capitalize() +
                       value_type.__name__.capitalize() + "PMap")

    if optional:
        def factory(argument):
            if argument is None:
                return None
            else:
                return TheMap(argument)
    else:
        factory = TheMap

    if initial is _UNDEFINED:
        initial = TheMap()
    else:
        initial = factory(initial)

    return field(mandatory=True, initial=initial,
                 type=optional_type(TheMap) if optional else TheMap,
                 factory=factory, invariant=invariant)


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

    The alias is always lower-cased since the resulting environment
    variables don't care about initial case of alias; upper and lower case
    versions result in same environment variable. We therefore want ``Link``
    comparison to be case-insensitive as far as aliases go.

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
    alias = field(
        mandatory=True, factory=lambda s: s.lower(),
        invariant=lambda s: (
            s.isalnum(), "Link aliases must be alphanumeric."
        )
    )


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

    :ivar PMap environment: Environment variables that should be exposed
        in the ``Application`` container, or ``None`` if no environment
        variables are specified.

    :ivar IRestartPolicy restart_policy: The restart policy for this
        application.

    :ivar command_line: Custom command to run using the image, a ``PVector``
        of ``unicode``. ``None`` means use default.

    :ivar bool running: Whether or not the application is running.
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
    running = field(mandatory=True, initial=True, type=bool)
    command_line = pvector_field(unicode, optional=True, initial=None)


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


def _keys_match(attribute):
    """
    Create an invariant for a ``field`` holding a ``pmap``.

    The invariant enforced is that the keys of the ``pmap`` equal the value of
    a particular attribute of the corresponding values.

    :param str attribute: The name of the attribute of the ``pmap`` values
        which must equal the corresponding key.
    :return: A function suitable for use as a pyrsistent invariant.
    """
    def key_match_invariant(pmap):
        # Either the field allows None, in which case this is necessary,
        # or it doesn't in which case this won't do any harm since
        # invalidity of None will be enforced elsewhere:
        if pmap is None:
            return (True, "")

        for (key, value) in pmap.items():
            if key != getattr(value, attribute):
                return (
                    False, "{} is not correct key for {}".format(key, value)
                )
        return (True, "")
    return key_match_invariant


# An invariant we use a couple times below in mappings from dataset_id to
# Dataset or Manifestation instances (or anything with a "dataset_id"
# attribute, really).
_keys_match_dataset_id = _keys_match("dataset_id")


class Node(PRecord):
    """
    Configuration for a single node on which applications will be managed
    (deployed, reconfigured, destroyed, etc).

    Manifestations attached to applications must also be present in the
    ``manifestations`` attribute.

    :ivar UUID uuid: The unique identifier for the node.

    :ivar applications: A ``PSet`` of ``Application`` instances describing
        the applications which are to run on this ``Node``.

    :ivar PMap manifestations: Mapping between dataset IDs and
        corresponding ``Manifestation`` instances that are present on the
        node. Includes both those attached as volumes to any applications,
        and those that are unattached. ``None`` if this information is
        unknown.
    """
    def __invariant__(self):
        manifestations = self.manifestations.values()
        for app in self.applications:
            if app.volume is not None:
                if app.volume.manifestation not in manifestations:
                    return (False, '%r manifestation is not on node' % (app,))
        return (True, "")

    def __new__(cls, hostname=None, **kwargs):
        # PRecord does some crazy stuff, thus _precord_buckets; see
        # PRecord.__new__.
        if "uuid" not in kwargs and "_precord_buckets" not in kwargs:
            # To be removed in https://clusterhq.atlassian.net/browse/FLOC-1795
            warn("UUID is required, this is for backwards compat with existing"
                 " tests only. If you see this in production code that's "
                 "a bug.", DeprecationWarning, stacklevel=2)
            kwargs["uuid"] = ip_to_uuid(hostname)
        return PRecord.__new__(cls, **kwargs)

    uuid = field(type=UUID, mandatory=True)
    applications = pset_field(Application)
    manifestations = pmap_field(
        unicode, Manifestation, invariant=_keys_match_dataset_id
    )


def same_node(node1, node2):
    """
    Return whether these two objects both refer to same cluster node,
    i.e. have same UUID.

    :param node1: ``Node`` or ``NodeState`` instance.
    :param node2: ``Node`` or ``NodeState`` instance.

    :return: Whether the two instances have same UUID.
    """
    return node1.uuid == node2.uuid


def _get_node(default_factory):
    """
    Create a helper function for getting a node from a deployment.

    :param default_factory: A one-argument callable which is called with the
        requested UUID when no matching node is found in the deployment.
        The return value is used as the result.

    :return: A two-argument callable which accepts a ``Deployment`` or a
             ``DeploymentState`` as the first argument and a ``unicode`` string
             giving a node hostname as the second argument.  It will return a
             node from the deployment object with a matching UUID or it
             will return a value from ``default_factory`` if no matching node
             is found.
    """
    def get_node(deployment, uuid, **defaults):
        nodes = list(
            node for node in deployment.nodes if node.uuid == uuid
        )
        if len(nodes) == 0:
            return default_factory(uuid=uuid, **defaults)
        return nodes[0]
    return get_node


class Deployment(PRecord):
    """
    A ``Deployment`` describes the configuration of a number of applications on
    a number of cooperating nodes.

    :ivar PSet nodes: A set containing ``Node`` instances
        describing the configuration of each cooperating node.
    """
    nodes = pset_field(Node)

    get_node = _get_node(Node)

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
            list(n for n in self.nodes if not same_node(n, node)) +
            [node]))

    def move_application(self, application, target_node):
        """
        Move an ``Application`` to a specified ``Node``, also moving any
        attached datasets.

        :param Application application: The ``Application`` to relocate.

        :param Node target_node: The desired ``Node`` to which the application
            should be moved.

        :return Deployment: Updated to reflect the new desired state.
        """
        deployment = self
        for node in deployment.nodes:
            for container in node.applications:
                if container.name == application.name:
                    # We only need to perform a move if the node currently
                    # hosting the container is not the node it's moving to.
                    if not same_node(node, target_node):
                        # If the container has a volume, we need to add the
                        # manifestation to the new host first.
                        if application.volume is not None:
                            dataset_id = application.volume.dataset.dataset_id
                            target_node = target_node.transform(
                                ("manifestations", dataset_id),
                                application.volume.manifestation
                            )
                        # Now we can add the application to the new host.
                        target_node = target_node.transform(
                            ["applications"], lambda s: s.add(application))
                        # And remove it from the current host.
                        node = node.transform(
                            ["applications"], lambda s: s.remove(application))
                        # Finally we can now remove the manifestation from the
                        # current host too.
                        if application.volume is not None:
                            dataset_id = application.volume.dataset.dataset_id
                            node = node.transform(
                                ("manifestations", dataset_id), discard
                            )
                        # Before updating the deployment instance.
                        deployment = deployment.update_node(node)
                        deployment = deployment.update_node(target_node)
        return deployment


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


@attributes(["going", "creating", "resizing", "deleting"])
class DatasetChanges(object):
    """
    The dataset-related changes necessary to change the current state to
    the desired state.

    :ivar frozenset going: The ``DatasetHandoff``\ s necessary to let
        other nodes take over hosting datasets being moved away from a
        node.  These must be handed off.

    :ivar frozenset creating: The ``Dataset``\ s necessary to let this
        node create any new datasets meant to be hosted on
        this node.  These must be created.

    :ivar frozenset resizing: The ``Dataset``\ s necessary to let this
        node resize any existing datasets that are desired somewhere on
        the cluster and locally exist with a different maximum_size to the
        desired maximum_size. These must be resized.

    :ivar frozenset deleting: The ``Dataset``\ s that should be deleted.
    """


class IClusterStateChange(Interface):
    """
    An ``IClusterStateChange`` can update a ``DeploymentState`` with new
    information.
    """
    def update_cluster_state(cluster_state):
        """
        :param DeploymentState cluster_state: Some current known state of the
            cluster.

        :return: A new ``DeploymentState`` similar to ``cluster_state`` but
            with changes from this object applied to it.
        """

    def get_information_wipe():
        """
        Create a ``IClusterStateWipe`` that can wipe information added by
        this change.

        For example, if this update adds information to a particular node,
        the returned ``IClusterStateChange`` will wipe out that
        information indicating ignorance about that information. We need
        this ability in order to expire out-of-date state information.

        :return: A ``IClusterStateWipe`` that undoes this update.
        """


class IClusterStateWipe(Interface):
    """
    An ``IClusterStateWipe`` can remove some information from a
    ``DeploymentState``.

    The type of a provider is implicitly part of its interface. Instances
    with different types will not replace each other, even if they have
    same key.
    """
    def update_cluster_state(cluster_state):
        """
        :param DeploymentState cluster_state: Some current known state of the
            cluster.

        :return: A new ``DeploymentState`` similar to ``cluster_state`` but
            with some information removed from it.
        """

    def key():
        """
        Return a key describing what information will be wiped.

        Providers that wipe the same information should return the same
        key, and providers that wipe different information should return
        differing keys.

        Different ``IClusterStateWipe`` implementors are presumed to
        cover different information, so there is no need for the key to
        express that differentation.
        """


class IClusterStateSource(Interface):
    """
    Represents where some cluster state (``IClusterStateChange``) came from.
    This is presently used for activity/inactivity tracking to inform change
    wiping.
    """
    def last_activity():
        """
        :return: The point in time at which the last activity was observed from
            this source.
        :rtype: ``datetime.datetime`` (in UTC)
        """


@implementer(IClusterStateSource)
class ChangeSource(object):
    """
    An ``IClusterStateSource`` which reports whatever time it was last told to
    report.

    :ivar float _last_activity: Recorded activity time.
    """
    def __init__(self):
        self.set_last_activity(0)

    def set_last_activity(self, since_epoch):
        """
        Set the time of the last activity.

        :param float since_epoch: Number of seconds since the epoch at which
            point the activity occurred.
        """
        self._last_activity = since_epoch

    def last_activity(self):
        return datetime.utcfromtimestamp(self._last_activity)


def ip_to_uuid(ip):
    """
    Deterministically convert IP to UUID.

    This is intended for interim use and backwards compatibility for
    existing tests. It should not be hit in production code paths.

    :param unicode ip: An IP.

    :return UUID: Matching UUID.
    """
    return UUID(bytes=md5(ip.encode("utf-8")).digest())


@implementer(IClusterStateChange)
class NodeState(PRecord):
    """
    The current state of a node.

    :ivar UUID uuid: The node's UUID.
    :ivar unicode hostname: The IP of the node.
    :ivar applications: A ``PSet`` of ``Application`` instances on this node,
        or ``None`` if the information is not known.
    :ivar used_ports: A ``PSet`` of ``int``\ s giving the TCP port numbers in
        use (by anything) on this node.
    :ivar PMap manifestations: Mapping between dataset IDs and corresponding
        ``Manifestation`` instances that are present on the node.  Includes
        both those attached as volumes to any applications, and those that are
        unattached.  ``None`` if this information is unknown.
    :ivar PMap paths: The filesystem paths of the manifestations on this node.
        Maps ``dataset_id`` to a ``FilePath``.
    :ivar PMap devices: The OS devices by which datasets are made manifest.
        Maps ``dataset_id`` (as a ``UUID``) to a ``FilePath``.
    """
    # Attributes that may be set to None to indicate ignorance:
    _POTENTIALLY_IGNORANT_ATTRIBUTES = ["used_ports", "applications",
                                        "manifestations", "paths",
                                        "devices"]

    # Dataset attributes that must all be non-None if one is non-None:
    _DATASET_ATTRIBUTES = {"manifestations", "paths", "devices"}

    # Application attributes that must all be non-None if one is non-None:
    _APPLICATION_ATTRIBUTES = {"applications", "used_ports"}

    def __invariant__(self):
        def _field_missing(fields):
            num_known_attributes = sum(getattr(self, name) is None
                                       for name in fields)
            return num_known_attributes not in (0, len(fields))
        for fields in (self._APPLICATION_ATTRIBUTES, self._DATASET_ATTRIBUTES):
            if _field_missing(fields):
                return (False,
                        "Either all or none of {} must be set.".format(fields))
        return (True, "")

    def __new__(cls, **kwargs):
        # PRecord does some crazy stuff, thus _precord_buckets; see
        # PRecord.__new__.
        if "uuid" not in kwargs and "_precord_buckets" not in kwargs:
            # To be removed in https://clusterhq.atlassian.net/browse/FLOC-1795
            warn("UUID is required, this is for backwards compat with existing"
                 " tests only. If you see this in production code that's "
                 "a bug.", DeprecationWarning, stacklevel=2)
            kwargs["uuid"] = ip_to_uuid(kwargs["hostname"])
        return PRecord.__new__(cls, **kwargs)

    uuid = field(type=UUID, mandatory=True)
    hostname = field(type=unicode, factory=unicode, mandatory=True)
    used_ports = pset_field(int, optional=True, initial=None)
    applications = pset_field(Application, optional=True, initial=None)
    manifestations = pmap_field(unicode, Manifestation, optional=True,
                                initial=None, invariant=_keys_match_dataset_id)
    paths = pmap_field(unicode, FilePath, optional=True, initial=None)
    devices = pmap_field(UUID, FilePath, optional=True, initial=None)

    def update_cluster_state(self, cluster_state):
        return cluster_state.update_node(self)

    def _provides_information(self):
        """
        Return whether the node has some information, i.e. is not completely
        ignorant.
        """
        return any(getattr(self, attr) is not None
                   for attr in self._POTENTIALLY_IGNORANT_ATTRIBUTES)

    def get_information_wipe(self):
        """
        The result wipes any attributes that are set by this instance
        (i.e. aren't ``None``), and will remove the ``NodeState``
        completely if result is ``NodeState`` with no knowledge of
        anything.
        """
        attributes = [attr for attr in
                      self._POTENTIALLY_IGNORANT_ATTRIBUTES
                      if getattr(self, attr) is not None]
        return _WipeNodeState(node_uuid=self.uuid, attributes=attributes)


@implementer(IClusterStateWipe)
class _WipeNodeState(PRecord):
    """
    Wipe information about a specific node from a ``DeploymentState``.

    Only specific attributes will be wiped. If all attributes have been
    wiped off the relevant ``NodeState`` then it will also be removed from
    the ``DeploymentState`` completely.

    :ivar UUID node_uuid: The UUID of the node being wiped.
    :ivar PSet attributes: Names of ``NodeState`` attributes to wipe.
    """
    node_uuid = field(mandatory=True, type=UUID)
    attributes = pset_field(str)

    def update_cluster_state(self, cluster_state):
        nodes = {n for n in cluster_state.nodes
                 if n.uuid == self.node_uuid}
        if not nodes:
            return cluster_state
        [original_node] = nodes
        updated_node = original_node.evolver()
        for attribute in self.attributes:
            updated_node = updated_node.set(attribute, None)
        updated_node = updated_node.persistent()
        final_nodes = cluster_state.nodes.discard(original_node)
        if updated_node._provides_information():
            final_nodes = final_nodes.add(updated_node)
        return cluster_state.set("nodes", final_nodes)

    def key(self):
        return (self.node_uuid, self.attributes)


class DeploymentState(PRecord):
    """
    A ``DeploymentState`` describes the state of the nodes in the cluster.

    :ivar PSet nodes: A set containing ``NodeState`` instances describing the
        state of each cooperating node.
    :ivar PMap nonmanifest_datasets: A mapping from dataset identifiers (as
        ``unicode``) to corresponding ``Dataset`` instances.  This mapping
        describes every ``Dataset`` which is known to exist as part of the
        cluster but which has no manifestation on any node in the cluster.
        Such datasets may not be possible with all backends (for example, P2P
        backends must always store datasets on some cluster node).  This
        mapping does not convey further backend-specific information; backends
        are responsible for maintaining or determining additional information
        themselves given a dataset identifier.  The ``Dataset`` instances which
        are values in this mapping convey discovered state, not configuration.
        The fields which are for conveying configuration will not be
        initialized to meaningful values (see
        https://clusterhq.atlassian.net/browse/FLOC-1247).
    """
    nodes = pset_field(NodeState)

    get_node = _get_node(NodeState)

    nonmanifest_datasets = pmap_field(
        unicode, Dataset, invariant=_keys_match_dataset_id
    )

    def update_node(self, node_state):
        """
        Create new ``DeploymentState`` based on this one which updates an
        existing ``NodeState`` with any known information from the given
        ``NodeState``.  Attributes which are set to ``None` on the given
        update, indicating ignorance, will not be changed in the result.

        The given ``NodeState`` will simply be added if it doesn't represent a
        node that is already part of the ``DeploymentState`` (based on UUID
        comparison).

        :param NodeState node: An update for ``NodeState`` with same UUID in
            this ``DeploymentState``.

        :return DeploymentState: Updated with new ``NodeState``.
        """
        nodes = {n for n in self.nodes if same_node(n, node_state)}
        if not nodes:
            return self.transform(["nodes"], lambda s: s.add(node_state))
        [original_node] = nodes
        updated_node = original_node.evolver()
        for key, value in node_state.items():
            if value is not None:
                updated_node = updated_node.set(key, value)
        return self.set(
            "nodes", self.nodes.discard(original_node).add(
                updated_node.persistent()))

    def all_datasets(self):
        """
        :returns: A generator of 2-tuple(``Dataset``, ``Nodestate`` or
            ``None``) for all the primary manifest datasets and non-manifest
            datasets in the ``DeploymentState``.
        """
        for node in self.nodes:
            if node.manifestations is None:
                continue
            for manifestation in node.manifestations.values():
                if manifestation.primary:
                    yield manifestation.dataset, node
        for dataset in self.nonmanifest_datasets.values():
            yield dataset, None


@implementer(IClusterStateChange)
class NonManifestDatasets(PRecord):
    """
    A ``NonManifestDatasets`` represents datasets which are known to exist but
    which have no manifestations anywhere in the cluster.
    """
    datasets = pmap_field(unicode, Dataset, invariant=_keys_match_dataset_id)

    def update_cluster_state(self, cluster_state):
        return cluster_state.set(nonmanifest_datasets=self.datasets)

    def get_information_wipe(self):
        """
        Result will wipe all information about non-manifest datasets.
        """
        return _NonManifestDatasetsWipe()


@implementer(IClusterStateWipe)
class _NonManifestDatasetsWipe(object):
    """
    Wipe object that does nothing.

    There's no point in wiping this information. Even if no relevant
    agents are connected the datasets probably still continue to exist
    unchanged, since they're not node-specific.
    """
    def key(self):
        return None

    def update_cluster_state(self, cluster_state):
        return cluster_state


# Classes that can be serialized to disk or sent over the network:
SERIALIZABLE_CLASSES = [
    Deployment, Node, DockerImage, Port, Link, RestartNever, RestartAlways,
    RestartOnFailure, Application, Dataset, Manifestation, AttachedVolume,
    NodeState, DeploymentState, NonManifestDatasets,
]
