# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.
"""
Operation to create a container.
"""

from functools import partial
from datetime import timedelta
from uuid import UUID, uuid4

from pyrsistent import PClass, field
from zope.interface import implementer

from flocker.apiclient import MountedDataset
from flocker.common import gather_deferreds, loop_until, timeout as _timeout
from flocker.control import DockerImage

from benchmark._interfaces import IProbe, IOperation
from benchmark.operations._common import select_node


DEFAULT_TIMEOUT = timedelta(minutes=10)


def loop_until_state_found(reactor, get_states, state_matches, timeout):
    """
    Loop until a state has been reached.

    :param get_states: Callable returning a Deferred firing with a list
        of states.
    :param state_matches: Callable that accepts a state parameter, and
        returns a boolean indicating whether the state matches.
    :param timedelta timeout: Maximum time to wait for state to be found.
    :return Deferred[Any]: The matching state.
    """
    def state_reached():
        d = get_states()

        def find_match(states):
            for state in states:
                if state_matches(state):
                    return state
            return None
        d.addCallback(find_match)

        return d

    d = loop_until(reactor, state_reached)
    _timeout(reactor, d, timeout.total_seconds())
    return d


def create_dataset(
    reactor, control_service, node_uuid, dataset_id, volume_size,
    timeout=DEFAULT_TIMEOUT
):
    """
    Create a dataset, then wait for it to be mounted.

    :param IReactorTime reactor: Twisted Reactor.
    :param IFlockerAPIV1Client control_service: Benchmark control
        service.
    :param UUID node_uuid: Node on which to create dataset.
    :param UUID dataset_id: ID for created dataset.
    :param int volume_size: Size of volume in bytes.
    :param timedelta timeout: Maximum time to wait for dataset to be
        mounted.
    :return Deferred[DatasetState]: The state of the created dataset.
    """

    d = control_service.create_dataset(
        primary=node_uuid,
        maximum_size=volume_size,
        dataset_id=dataset_id,
    )

    def dataset_matches(dataset, state):
        return (
            state.dataset_id == dataset.dataset_id and
            state.primary == dataset.primary and
            state.path is not None
        )

    d.addCallback(
        lambda dataset: loop_until_state_found(
            reactor, control_service.list_datasets_state,
            partial(dataset_matches, dataset), timeout
        )
    )

    return d


def create_container(
    reactor, control_service, node_uuid, name, image, volumes=None,
    timeout=DEFAULT_TIMEOUT
):
    """
    Create a container, then wait for it to be running.

    :param IReactorTime reactor: Twisted Reactor.
    :param IFlockerAPIV1Client control_service: Benchmark control
        service.
    :param UUID node_uuid: Node on which to start the container.
    :param unicode name: Name of the container.
    :param DockerImage image: Docker image for the container.
    :param Optional[Sequence[MountedDataset]] volumes: Volumes to attach
        to the container.
    :param timedelta timeout: Maximum time to wait for container to be
        created.
    :return Deferred[ContainerState]: The state of the created container.
    """

    d = control_service.create_container(node_uuid, name, image, volumes)

    def container_matches(container, state):
        return (
            container.name == state.name and
            container.node_uuid == state.node_uuid and
            state.running
        )

    d.addCallback(
        lambda container: loop_until_state_found(
            reactor, control_service.list_containers_state,
            partial(container_matches, container), timeout
        )
    )

    return d


def delete_container(reactor, control_service, container):
    """
    Delete a container, then wait for it to be removed.

    :param IReactorTime reactor: Twisted Reactor.
    :param IFlockerAPIV1Client control_service: Benchmark control
        service.
    :param ContainerState container: Container to be removed.
    :return Deferred[ContainerState]: The state before removal.
    """

    def container_removed(expected):
        """
        Check whether a container has been removed (deleted and stopped).

        :param ContainerState expected: A container state to match against the
            results of ``list_containers_state``.
        :return Deferred[Optional[ContainerState]]: ``None`` if the
            ``expected`` container is found, or ``expected`` if it is not
            found.
        """
        d = control_service.list_containers_state()

        def container_matches(inspecting, expected):
            return (
                expected.name == inspecting.name and
                expected.node_uuid == inspecting.node_uuid and
                inspecting.running
            )

        def no_running_match(existing_state):
            for state in existing_state:
                if container_matches(state, expected):
                    return None
            return expected
        d.addCallback(no_running_match)
        return d

    d = control_service.delete_container(container.name)

    def loop_until_container_removed(_ignore):
        return loop_until(reactor, partial(container_removed, container))
    d.addCallback(loop_until_container_removed)

    return d


@implementer(IProbe)
class CreateContainerProbe(PClass):
    """
    Probe to create a container and wait for cluster to converge.
    """

    reactor = field(mandatory=True)
    control_service = field(mandatory=True)
    node_uuid = field(type=UUID, mandatory=True)
    name = field(type=unicode, mandatory=True)
    image = field(mandatory=True)
    dataset_id = field(type=UUID, mandatory=True)
    mountpoint = field(type=unicode, mandatory=True)

    @classmethod
    def setup(
        cls, reactor, control_service, name, image, volume_size, mountpoint
    ):
        """
        Create a probe.

        :param IReactorTime reactor: Twisted Reactor.
        :param IFlockerAPIV1Client control_service: Benchmark control service.
        :param unicode name: Name for created container.
        :param DockerImage image: Docker image for the container.
        :param int volume_size: Size of created volume, in bytes.
        :param unicode mountpoint: Mountpoint for created volume.
        :return: Deferred firing with a new probe.
        """
        # Select an arbitrary node on which to create the container.
        d = control_service.list_nodes().addCallback(select_node)

        def parallel_setup(node):
            # Ensure the Docker image is cached by starting and stopping a
            # container.
            name = unicode(uuid4())
            container_setup = create_container(
                reactor, control_service, node.uuid, name, image
            )
            container_setup.addCallback(
                partial(delete_container, reactor, control_service)
            )

            # Create the dataset
            dataset_id = uuid4()
            dataset_setup = create_dataset(
                reactor, control_service, node.uuid, dataset_id, volume_size
            )

            d = gather_deferreds((container_setup, dataset_setup))

            # Return only the dataset state
            d.addCallback(lambda results: results[1])

            return d
        d.addCallback(parallel_setup)

        # Create the CreateContainerProbe instance.
        def create_probe(dataset_state):
            return cls(
                reactor=reactor,
                control_service=control_service,
                node_uuid=dataset_state.primary,
                name=name,
                image=image,
                dataset_id=dataset_state.dataset_id,
                mountpoint=mountpoint,
            )
        d.addCallback(create_probe)

        return d

    def run(self):
        """
        Create a stateful container, and wait for it to be running.
        """
        volumes = [
            MountedDataset(
                dataset_id=self.dataset_id, mountpoint=self.mountpoint
            )
        ]

        d = create_container(
            self.reactor, self.control_service, self.node_uuid, self.name,
            self.image, volumes
        )

        return d

    def cleanup(self):
        """
        Delete the container and dataset created by the probe.
        """
        d = self.control_service.delete_container(self.name)

        d.addCallback(
            lambda _ignore: self.control_service.delete_dataset(
                self.dataset_id
            )
        )

        return d


@implementer(IOperation)
class CreateContainer(object):

    def __init__(
        self, reactor, cluster, image=u'clusterhq/mongodb', volume_size=None,
        mountpoint=u'/data'
    ):
        self.reactor = reactor
        self.control_service = cluster.get_control_service(reactor)
        self.image = DockerImage(repository=image)
        if volume_size is None:
            self.volume_size = cluster.default_volume_size()
        else:
            self.volume_size = volume_size
        self.mountpoint = mountpoint

    def get_probe(self):
        return CreateContainerProbe.setup(
            self.reactor,
            self.control_service,
            unicode(uuid4()),
            self.image,
            self.volume_size,
            self.mountpoint,
        )
