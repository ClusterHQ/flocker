# Copyright ClusterHQ Inc.  See LICENSE file for details.
import sys
from itertools import repeat
from ipaddr import IPAddress
from functools import partial
from uuid import uuid4
from bitmath import GiB

from eliot import add_destination, Message
from twisted.internet.defer import inlineCallbacks
from twisted.python.filepath import FilePath
from twisted.python import usage

from flocker.common import loop_until, gather_deferreds
from flocker.control.httpapi import REST_API_PORT
from flocker.control import DockerImage
from flocker.apiclient import FlockerClient, MountedDataset


def eliot_output(message):
    """
    Write pretty versions of eliot log messages to stdout.
    """
    message_action = message.get('action')

    if message_action is not None:
        msg = "%s\n" % message_action
        sys.stdout.write(msg)
        sys.stdout.flush()


class ContainerOptions(usage.Options):
    """
    Parses the options passed as an argument to the create container script.
    """
    description = "Set up containers in a Flocker cluster."

    optParameters = [
        ['apps-per-node', None, 1, 'Number of application containers per node',
         int],
        ['image', None, None,
         'Docker image to deploy'],
        ['mountpoint', None, None,
         'Location of the mountpoint of the datasets'],
        ['control-node', None, None,
         'Public IP address of the control node'],
        ['cert-directory', None, None,
         'Location of the user and control certificates and user key'],
        ['max-size', None, 1,
         'Size of the volume, in gigabytes. One GB by default'],
        ['wait', None, 7200,
         "The timeout in seconds for waiting until the operation is complete. "
         "Waits two hours by default."],
        ['wait-interval', None, 4,
         "How often are we going to check if the creation of containers and "
         "datasets has finished, in second"],
    ]

    synopsis = ('Usage: setup-cluster-containers --app-per-node <containers '
                'per node> --image<DockerImage> '
                '--mountpoint <path to the mountpoint> '
                '--control-node <IPAddress> '
                '--cert-directory <path where all the certificates are> '
                '[--max-size <volume size in GB>] '
                '[--wait <total seconds to wait>]'
                '[--wait-interval <seconds to wait between list calls]')

    def postOptions(self):
        # Mandatory parameters
        # Validate image
        if self['image'] is None:
            raise usage.UsageError(
                "image parameter must be provided"
            )
        # Validate mountpoint
        if self['mountpoint'] is None:
            raise usage.UsageError("mountpoint is a mandatory parameter")
        else:
            try:
                FilePath(self['mountpoint'])
            except ValueError:
                raise usage.UsageError("mountpoint has to be an absolute path")
        # Validate app per node
        if self['apps-per-node'] is None:
            raise usage.UsageError("apps-per-node is a mandatory parameter")
        else:
            try:
                self['apps-per-node'] = int(self['apps-per-node'])
            except ValueError:
                raise usage.UsageError("apps-per-node has to be an integer")
        # Validate control node
        if self['control-node'] is None:
            raise usage.UsageError("control-node is a mandatory parameter")
        else:
            try:
                IPAddress(self['control-node'])
            except ValueError:
                raise usage.UsageError("control-node has to be an IP address")
        # Validate certificate directory
        if self['cert-directory'] is None:
            raise usage.UsageError("cert-directory is a mandatory parameter")

        # Validate optional parameters
        # Note that we don't check if those parameters are None, because
        # all of them have default value and can't be none. If they are,
        # and exception will be raised
        try:
            self['max-size'] = int(self['max-size'])
        except ValueError:
            raise usage.UsageError(
                "The max-size timeout must be an integer.")

        try:
            self['wait'] = int(self['wait'])
        except ValueError:
            raise usage.UsageError("The wait timeout must be an integer.")

        try:
            self['wait-interval'] = int(self['wait-interval'])
        except ValueError:
            raise usage.UsageError(
                "The wait-interval must be an integer.")


def main(reactor, argv, environ):
    # Setup eliot to print better human-readable output to standard
    # output
    add_destination(eliot_output)

    try:
        options = ContainerOptions()
        options.parseOptions(argv[1:])
    except usage.UsageError as e:
        sys.stderr.write(e.args[0])
        sys.stderr.write('\n\n')
        sys.stderr.write(options.getSynopsis())
        sys.stderr.write('\n')
        sys.stderr.write(options.getUsage())
        raise SystemExit(1)

    container_deployment = ClusterContainerDeployment.from_options(reactor,
                                                                   options)

    def deploy_and_wait(cluster_container_deployment):
        return cluster_container_deployment.deploy_and_wait_for_creation()

    container_deployment.addCallback(deploy_and_wait)

    return container_deployment


class ClusterContainerDeployment(object):
    """
    Class that contains all the methods needed to deploy a new config in a
    cluster.

    :ivar image: ``DockerImage`` for the containers.
    :ivar max_size: maximum volume (dataset) size in bytes.
    :ivar mountpoint: unicode string containing the absolute path of the
        mountpoint.
    :ivar per_node: number of containers and dataset per node.
    :ivar control_node_address: public ip address of the control node.
    :ivar timeout: total time to wait for the containers and datasets
        to be created.
    :ivar wait_interval: how much to wait between list calls when waiting for
        the containers and datasets to be created.
    :ivar _num_loops: number of times to repeat the looping call based on the
        ``tiemeout`` and the ``wait_interval``.
    :ivar cluster_cert: ``FilePath`` of the cluster certificate.
    :ivar user_cert: ``FilePath`` of the user certificate.
    :ivar user_key: ``FilePath`` of the user key.
    :ivar _initial_num_datasets: number of datasets that are already present
        in the cluster.
    :ivar _initial_num_containers: number of containers that are already
        present in the cluster.
    :ivar client: ``FlockerClient`` conected to the cluster.
    :ivar reactor: ``Reactor`` used by the client.
    :ivar nodes: list of `Node` returned by client.list_nodes
    """
    def __init__(self, reactor, image, max_size, mountpoint, per_node,
                 control_node_address, timeout, wait_interval, cluster_cert,
                 user_cert, user_key, initial_num_datasets,
                 initial_num_containers, client, nodes):
        """
        ``ClusterContainerDeployment`` constructor.
        It is not meant to be called directly. See ``from_options`` if you
        want to instantiate a ``ClusterContainerDeployment`` object.

        """
        self.image = image
        self.max_size = max_size
        self.mountpoint = mountpoint
        self.per_node = per_node
        self.control_node_address = control_node_address
        self.timeout = timeout
        self.wait_interval = wait_interval
        if self.timeout is None:
            # Wait two hours by default
            self.timeout = 72000
        self._num_loops = 1
        if self.wait_interval < self.timeout:
            self._num_loops = self.timeout / self.wait_interval

        self.cluster_cert = cluster_cert
        self.user_cert = user_cert
        self.user_key = user_key
        self._initial_num_datasets = initial_num_datasets
        self._initial_num_containers = initial_num_containers
        self.client = client
        self.reactor = reactor
        self.nodes = nodes

    @classmethod
    def from_options(cls, reactor, options):
        """
        Create a cluster container deployment object from the
        options given through command line.

        :param reactor: reactor
        :param options: ``ContainerOptions`` container the parsed
            options given to the script.
        """
        try:
            image = DockerImage(repository=options['image'])
            max_size = int(GiB(options['max-size']).to_Byte().value)
            mountpoint = unicode(options['mountpoint'])
            per_node = options['apps-per-node']
            control_node_address = options['control-node']
            timeout = options['wait']
            wait_interval = options['wait-interval']

        except Exception as e:
            sys.stderr.write("%s: %s\n" % ("Missing or wrong arguments", e))
            sys.stderr.write(e.args[0])
            sys.stderr.write('\n\n')
            sys.stderr.write(options.getSynopsis())
            sys.stderr.write('\n')
            sys.stderr.write(options.getUsage())
            raise SystemExit(1)

        certificates_path = FilePath(options['cert-directory'])
        cluster_cert = certificates_path.child(b"cluster.crt")
        user_cert = certificates_path.child(b"user.crt")
        user_key = certificates_path.child(b"user.key")

        # Initialise client
        client = FlockerClient(
            reactor,
            control_node_address,
            REST_API_PORT,
            cluster_cert,
            user_cert,
            user_key
        )

        nodes = []
        datasets = []
        containers = []

        # Listing datasets and containers to know the initial number of
        # datasets and containers, so we know the total number of them
        # we are expecting to have.
        # XXX please note that, if some of those initial datasets or containers
        # are being deleted, the output of this script won't be as expected,
        # and it will end up timing out waiting for all the containers and
        # datasets to be ready. This is a possible future improvement (bear
        # it in mind if reusing the code), but it is not needed by benchmarking
        # as it is not an scenario we will have, and even if we had it, we
        # still can re-run this script to create the extra datasets and
        # containers we may need, or even cleanup the cluster and start again.
        def list_datasets(ignored):
            return client.list_datasets_state()

        def list_containers(ignored):
            return client.list_containers_state()

        d = client.list_nodes()
        d.addCallback(nodes.extend)
        d.addCallback(list_datasets)
        d.addCallback(datasets.extend)
        d.addCallback(list_containers)
        d.addCallback(containers.extend)

        def create_instance(ignored):
            return cls(reactor, image, max_size, mountpoint, per_node,
                       control_node_address, timeout, wait_interval,
                       cluster_cert,
                       user_cert, user_key, len(datasets),
                       len(containers), client, nodes)

        d.addCallback(create_instance)

        return d

    def _dataset_to_volume(self, dataset):
        """
        Given a ``Dataset``, returns a ``MountedDataset`` populated with
        the information from the dataset and the mountpoint.

        :param dataset: ``Dataset`` containing the dataset_id of an
            existent dataset.

        :return MountedDataset: with the datset id and the mountpoint
            populated.
        """
        if dataset is not None:
            return MountedDataset(dataset_id=dataset.dataset_id,
                                  mountpoint=self.mountpoint)
        else:
            return None

    def _set_nodes(self, nodes):
        """
        Set the list of the nodes in the cluster.

        :param nodes: list of ``Node`` containing all the nodes in the
            cluster.
        """
        self.nodes = nodes

    def deploy(self):
        """
        Deploy the new configuration: create the requested containers
        and dataset in the cluster nodes.

        :return Deferred: that will fire once the request to create all
            the containers and datasets has been sent.
        """
        Message.log(action="Listing current nodes")
        d = self.client.list_nodes()
        d.addCallback(self._set_nodes)
        d.addCallback(self._set_current_number_of_datasets_and_containers)
        d.addCallback(self.create_datasets_and_containers)
        return d

    def _set_current_number_of_datasets_and_containers(self, ignored):
        """
        Populates the ``self._initial_num_containers`` with the current
        number of containers in the cluster. It is intended to be used
        before requesting the creation of any containers or datasets so
        we can know the total number of datasets and containers to expect.

        :return Deferred: that will fire once the ``_initial_num_datasets``
            and ``_initial_num_containers`` are populated.
        """
        d1 = self.client.list_containers_state()

        def set_initial_num_containers(containers):
            self._initial_num_containers = len(containers)

        d1.addCallback(set_initial_num_containers)

        d2 = self.client.list_datasets_state()

        def set_initial_num_datasets(datasets):
            self._initial_num_datasets = len(datasets)

        d2.addCallback(set_initial_num_datasets)

        return gather_deferreds([d1, d2])

    def is_datasets_deployment_complete(self):
        """
        Check if all the dataset have been created.

        :return Deferred: that will fire once the list datasets call
            has been completed, and which result will bee True if all the
            dataset have been created, or false otherwise.
        """
        number_of_datasets = self.per_node * len(self.nodes)

        d = self.client.list_datasets_state()

        def do_we_have_enough_datasets(datasets):
            created_datasets = len(datasets) - self._initial_num_datasets
            msg = (
                "Waiting for the datasets to be ready..."
                "Created {current_datasets} of {datasets_to_create} "
                "(Total = {total_datasets})"

            ).format(
                current_datasets=created_datasets,
                datasets_to_create=number_of_datasets,
                total_datasets=len(datasets),
            )
            Message.log(action=msg)

            return (created_datasets >= number_of_datasets)

        d.addCallback(do_we_have_enough_datasets)
        return d

    def is_container_deployment_complete(self):
        """
        Check if all the containers have been created.

        :return Deferred: that will fire once the list containers call
            has been completed, and which result will bee True if all the
            containers have been created, or False otherwise.
        """
        number_of_containers = self.per_node * len(self.nodes)

        d = self.client.list_containers_state()

        def do_we_have_enough_containers(containers):
            created_containers = len(containers) - self._initial_num_containers
            msg = (
                "Waiting for the containers to be ready..."
                "Created {current_containers} of {containers_to_create} "
                "(Total = {total_containers})"

            ).format(
                current_containers=created_containers,
                containers_to_create=number_of_containers,
                total_containers=len(containers),
            )
            Message.log(action=msg)
            return (created_containers >= number_of_containers)

        d.addCallback(do_we_have_enough_containers)
        return d

    @inlineCallbacks
    def deploy_and_wait_for_creation(self):
        """
        Function that will deploy the new configuration (create all the
        dataset and container requested) and will only return once all
        of them have been created.
        """
        yield self.deploy()
        yield loop_until(self.reactor,
                         self.is_datasets_deployment_complete,
                         repeat(self.wait_interval, self._num_loops))
        yield loop_until(self.reactor,
                         self.is_container_deployment_complete,
                         repeat(self.wait_interval, self._num_loops))

    def create_datasets_and_containers(self, ignored=None):
        """
        Create ``per_node`` containers and datasets in each node of the
        cluster.

        :return Deferred: once all the requests to create the datasets and
            containers are made.
        """
        deferred_list = []
        for node in self.nodes:
            create_container_in_node = partial(self.create_container,
                                               node=node)
            for i in range(self.per_node):
                msg = (
                    "Creating dataset {num_dataset} in node {node_uuid}"

                ).format(
                    num_dataset=i+1,
                    node_uuid=node.uuid,
                )
                Message.log(action=msg)

                d = self.client.create_dataset(node.uuid,
                                               maximum_size=self.max_size)
                d.addCallback(create_container_in_node)
                deferred_list.append(d)

        return gather_deferreds(deferred_list)

    def create_container(self, dataset, node):
        """
        Create a container in the given node with the give dataset attached.

        :param dataset: ``Dataset`` to attach to the container.
        :param node: ``Node`` where to create the container.

        :return Deferred: that will fire once the request to create the
            container is made.
        """
        msg = (
            "Creating container in node {node_uuid} with attached "
            "dataset {dataset_id}"

        ).format(
            node_uuid=node.uuid,
            dataset_id=dataset.dataset_id
        )
        Message.log(action=msg)

        return self.client.create_container(node.uuid,
                                            unicode(uuid4()),
                                            self.image,
                                            volumes=[self._dataset_to_volume
                                                     (dataset)])
