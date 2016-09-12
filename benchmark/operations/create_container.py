# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.
"""
Operation to create a container.
"""

from functools import partial
from uuid import UUID, uuid4

from pyrsistent import PClass, field
from zope.interface import implementer

from flocker.apiclient import MountedDataset
from flocker.common import gather_deferreds
from flocker.control import DockerImage

from benchmark._flocker import (
    create_dataset, create_container, delete_container
)
from benchmark._interfaces import IProbe, IOperation
from benchmark.operations._common import select_node


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
