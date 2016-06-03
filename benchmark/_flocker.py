# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.
"""
Utilities to perform Flocker operations.
"""

from functools import partial
from datetime import timedelta
from itertools import repeat

from flocker.common import loop_until, timeout as _timeout

DEFAULT_TIMEOUT = timedelta(minutes=10)


def loop_until_state_found(reactor, get_states, state_matches, timeout):
    """
    Loop until a state has been reached.

    :param IReactorTime reactor: Twisted Reactor.
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

    d = loop_until(reactor, state_reached, repeat(10.0))
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

    def wait_until_running(container):
        def container_matches(container, state):
            return (
                container.name == state.name and
                container.node_uuid == state.node_uuid and
                state.running
            )

        d = loop_until_state_found(
            reactor, control_service.list_containers_state,
            partial(container_matches, container), timeout
        )

        # If an error occurs, delete container, but return original failure
        def delete_container(failure):
            d = control_service.delete_container(container.name)
            d.addCallback(lambda _ignore: failure)
            return d
        d.addErrback(delete_container)

        return d
    d.addCallback(wait_until_running)

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
