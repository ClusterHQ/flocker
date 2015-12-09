# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for using libcloud.
"""

from time import sleep
from zope.interface import implementer

from characteristic import attributes, Attribute

from twisted.python.reflect import fullyQualifiedName
from twisted.conch.ssh.keys import Key

from eliot import Message, write_traceback

from flocker.provision._ssh import run_remotely, run_from_args

from ._common import INode, IProvisioner

from ..common import poll_until

from libcloud.compute.types import NodeState


def get_size(driver, size_id):
    """
    Return a ``NodeSize`` corresponding to a given id.

    :param driver: The libcloud driver to query for sizes.
    """
    try:
        return [s for s in driver.list_sizes() if s.id == size_id][0]
    except IndexError:
        raise ValueError("Unknown size.", size_id)


def get_image(driver, image_name):
    """
    Return a ``NodeImage`` corresponding to a given name of size.

    :param driver: The libcloud driver to query for images.
    """
    try:
        return [s for s in driver.list_images() if s.name == image_name][0]
    except IndexError:
        raise ValueError("Unknown image.", image_name)


@implementer(INode)
@attributes([
    # _node gets updated, so we can't make this immutable.
    Attribute('_node'),
    Attribute('_provisioner'),
    'address',
    'private_address',
    'distribution',
])
class LibcloudNode(object):
    """
    A node created with libcloud.

    :ivar Node _node: The libcloud node object.
    :ivar LibcloudProvisioner _provisioner: The provisioner that created this
        node.
    :ivar bytes address: The IP address of the node.
    :ivar str distribution: The distribution installed on the node.
    :ivar bytes name: The name of the node.
    """

    def destroy(self):
        """
        Destroy the node.
        """
        self._node.destroy()

    def reboot(self):
        """
        Reboot the node.

        :return Effect:
        """

        def do_reboot(_):
            self._node.reboot()
            self._node, self.addresses = (
                self._node.driver.wait_until_running(
                    [self._node], wait_period=15)[0])
            return

        return run_remotely(
            username="root",
            address=self.address,
            commands=run_from_args(["sync"])
        ).on(success=do_reboot)

    def get_default_username(self):
        """
        Return the default username on this provisioner.
        """
        return self._provisioner._get_default_user(self.distribution)

    def provision(self, package_source, variants=()):
        """
        Provision flocker on this node.

        :param PackageSource package_source: The source from which to install
            flocker.
        :param set variants: The set of variant configurations to use when
            provisioning
        """
        return self._provisioner._provision(
            node=self,
            package_source=package_source,
            distribution=self.distribution,
            variants=variants,
        ).on(success=lambda _: self.address)

    @property
    def name(self):
        return self._node.name


class CloudKeyNotFound(Exception):
    """
    Raised if the cloud provider doesn't have a ssh-key with a given name.
    """


@implementer(IProvisioner)
@attributes([
    Attribute('_driver'),
    Attribute('_keyname'),
    Attribute('_image_names'),
    Attribute('_create_node_arguments'),
    Attribute('_provision'),
    Attribute('_default_size'),
    Attribute('_get_default_user'),
    Attribute('_use_private_addresses', instance_of=bool, default_value=False),
], apply_immutable=True)
class LibcloudProvisioner(object):
    """
    :ivar libcloud.compute.base.NodeDriver _driver: The libcloud driver to use.
    :ivar bytes _keyname: The name of an existing ssh public key configured
        with the cloud provider. The provision step assumes the corresponding
        private key is available from an agent.
    :ivar dict _image_names: Dictionary mapping distributions to cloud image
        names.
    :ivar callable _create_node_arguments: Extra arguments to pass to
        libcloud's ``create_node``.
    :ivar callable _provision: Function to call to provision a node.
    :ivar str _default_size: Name of the default size of node to create.
    :ivar callable get_default_user: Function to provide the default
        username on the node.
    :ivar bool _use_private_addresses: Whether the `private_address` of nodes
        should be populated. This should be specified if the cluster nodes
        use the private address for inter-node communication.
    """

    def get_ssh_key(self):
        """
        Return the public key associated with the provided keyname.

        :return Key: The ssh public key or ``None`` if it can't be determined.
        """
        try:
            key_pair = self._driver.get_key_pair(self._keyname)
        except Exception as e:
            if "RequestLimitExceeded" in e.message:
                # If we have run into API limits, we don't know if the key is
                # available. Re-raise the the exception, so that we can
                # accurately see the cause of the error.
                raise
            raise CloudKeyNotFound(self._keyname)
        if key_pair.public_key is not None:
            return Key.fromString(key_pair.public_key, type='public_openssh')
        else:
            # EC2 only provides the SSH2 fingerprint (for uploaded keys)
            # or the SHA-1 hash of the private key (for EC2 generated keys)
            # https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_KeyPairInfo.html
            return None

    def create_node(self, name, distribution,
                    size=None, disk_size=8,
                    metadata={}):
        """
        Create a node.  If at first this does not succeed, try, try again.

        :param str name: The name of the node.
        :param str distribution: The name of the distribution to install on the
            node.
        :param str size: The name of the size to use.
        :param int disk_size: The size of disk to allocate.
        :param dict metadata: Metadata to associate with the node.

        :return libcloud.compute.base.Node: The created node.
        """
        if size is None:
            size = self._default_size

        image_name = self._image_names[distribution]

        create_node_arguments = self._create_node_arguments(
            disk_size=disk_size)

        node, addresses = self._create_with_retry(
            name=name,
            image=get_image(self._driver, image_name),
            size=get_size(self._driver, size),
            ex_keyname=self._keyname,
            ex_metadata=metadata,
            **create_node_arguments
        )

        public_address = addresses[0]
        if isinstance(public_address, unicode):
            public_address = public_address.encode("ascii")

        if self._use_private_addresses:
            private_address = node.private_ips[0]
        else:
            private_address = None

        if isinstance(private_address, unicode):
            private_address = private_address.encode("ascii")

        return LibcloudNode(
            provisioner=self,
            node=node, address=public_address,
            private_address=private_address,
            distribution=distribution)

    def _create_with_retry(self, **kwargs):
        """
        Create a compute instance.  Clean up failed attempts and retry if
        necessary.
        """
        return poll_until(lambda: self._get_node(**kwargs), iter([15] * 10))

    def _get_node(self, name, **kwargs):
        """
        Create a compute instance.

        :return: If the node is created successfully, a two-tuple of the
            libcloud node object and the instance's public IP address.  If an
            error occurs creating the node, ``None``.
        """
        try:
            node = self._driver.create_node(name=name, **kwargs)
        except:
            # We don't know if we just created a node or not.  Look for it and
            # destroy it if we did.  Hopefully we don't encounter too many more
            # errors on the way.
            self._cleanup_node_named(name)
            raise

        # libcloud has wait_until_running but it doesn't understand the error
        # state that Rackspace instances often go in to.  It will keep waiting
        # for the instance to get to the running state even after it has gone
        # to the error state.  Eventually it will time out, but only after
        # waiting for much longer than necessary.
        #
        # So do a loop ourselves.

        # Here are the states that indicate we've either succeeded or failed.
        # Only RUNNING indicates success.  The rest are failure states.  Once
        # the node is in one of those states, it makes no sense to keep
        # waiting.
        terminal_states = {
            NodeState.RUNNING,
            NodeState.ERROR,
            NodeState.TERMINATED,
            NodeState.STOPPED,
            NodeState.SUSPENDED,
            NodeState.PAUSED,
        }

        try:
            poll_until(
                predicate=lambda: self._node_in_state(node, terminal_states),
                # Overall retry sleep time (not quite the same as timeout since
                # it doesn't count time spent in the predicate) is just copied
                # from the default libcloud timeout for wait_until_running.
                # Maybe some other value would be better.
                steps=iter([15] * (600 / 15)),
            )

            if self._node_in_state(node, {NodeState.RUNNING}):
                # Success!  Now ask libcloud to dig out the details for us.
                # Use a low timeout because we just saw that we're running
                # already.
                #
                # XXX We want retry on random network errors here.  We don't
                # want it on the timeout case, though, since that probably
                # means something went crazy wrong.  Maybe?  Perhaps it only
                # adds about 10 seconds to the overall time spent before we
                # fail, though, which isn't that bad.
                return _retry_exception(
                    lambda: self._driver.wait_until_running([node], timeout=1)
                )[0]
            else:
                # Destroy it and indicate failure to the caller by returning
                # None
                _retry_exception(node.destroy)
                return None
        except:
            # If we're going to raise some exception instead of returning the
            # node, destroy the node so it doesn't leak.  No one else is going
            # to take any responsibility for cleaning it up.
            _retry_exception(node.destroy)
            raise

    def _node_in_state(self, target_node, target_states):
        """
        Determine whether a compute instance is in one of the given states.

        :param target_node: A libcloud node object representing the compute
            instance to examine.
        :param set target_states: The states to compare the compute instance's
            actual state against.

        :return: ``True`` if the compute instance is currently in one of
            ``target_states``, ``False`` otherwise.
        """
        nodes = _retry_exception(self._driver.list_nodes)
        for node in nodes:
            if node.uuid == target_node.uuid:
                return node.state in target_states
        return False

    def _cleanup_node_named(self, name):
        """
        Destroy a node with the given name, if there is one.  Otherwise, do
        nothing.
        """
        nodes = _retry_exception(self._driver.list_nodes)
        for node in nodes:
            if node.name == name:
                Message.new(
                    message_type=(
                        u"flocker:provision:libcloud:cleanup_node_named"
                    ),
                    name=name,
                    id=node.id,
                    state=node.state,
                ).write()
                _retry_exception(node.destroy)
                return


def _retry_exception(f, steps=(0.1,) * 10, sleep=sleep):
    """
    Retry a function if it raises an exception.

    :return: Whatever the function returns.
    """
    steps = iter(steps)

    while True:
        try:
            Message.new(
                message_type=(
                    u"flocker:provision:libcloud:retry_exception:trying"
                ),
                function=fullyQualifiedName(f),
            ).write()
            return f()
        except:
            # Try to get the next sleep time from the steps iterator.  Do it
            # without raising an exception (StopIteration) to preserve the
            # current exception context.
            for step in steps:
                write_traceback()
                sleep(step)
                break
            else:
                # Didn't hit the break, so didn't iterate at all, so we're out
                # of retry steps.  Fail now.
                raise
