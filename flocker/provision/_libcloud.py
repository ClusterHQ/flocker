# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for using libcloud.
"""
import socket

from time import sleep
from zope.interface import implementer

from characteristic import attributes, Attribute

from twisted.internet.defer import DeferredList, maybeDeferred
from twisted.python.reflect import fullyQualifiedName
from twisted.conch.ssh.keys import Key

from eliot import Message, start_action, write_failure, write_traceback
from eliot.twisted import DeferredContext

from flocker.provision._ssh import run_remotely, run_from_args

from ._common import INode, IProvisioner

from ..common import loop_until, poll_until
from ..common._retry import function_serializer

from libcloud.compute.types import NodeState
from libcloud.utils.networking import is_valid_ip_address


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
    image_names = list(s.name for s in driver.list_images())
    try:
        return list(n for n in image_names if n == image_name)[0]
    except IndexError:
        raise ValueError("Unknown image.", image_name, image_names)


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
    # Here are the states that indicate we've either succeeded or failed.
    # Only RUNNING indicates success.  The rest are failure states.  Once
    # the node is in one of those states, it makes no sense to keep
    # waiting.
    TERMINAL_STATES = {
        NodeState.RUNNING,
        NodeState.ERROR,
        NodeState.TERMINATED,
        NodeState.STOPPED,
        NodeState.SUSPENDED,
        NodeState.PAUSED,
    }

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
            raise CloudKeyNotFound("{}: {}".format(self._keyname, str(e)))
        if key_pair.public_key is not None:
            return Key.fromString(key_pair.public_key, type='public_openssh')
        else:
            # EC2 only provides the SSH2 fingerprint (for uploaded keys)
            # or the SHA-1 hash of the private key (for EC2 generated keys)
            # https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_KeyPairInfo.html
            return None

    def create_node(self, name, distribution, metadata={}):
        """
        Create a node.  If at first this does not succeed, try, try again.

        :param str name: The name of the node.
        :param str distribution: The name of the distribution to install on the
            node.
        :param dict metadata: Metadata to associate with the node.

        :return libcloud.compute.base.Node: The created node.
        """
        size = self._default_size

        try:
            image_name = self._image_names[distribution]
        except KeyError:
            raise Exception(
                "Distribution not supported with provider",
                distribution,
                self._driver.name,
            )

        create_node_arguments = self._create_node_arguments()

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
        try:
            poll_until(
                lambda: self._node_in_state(node, self.TERMINAL_STATES),
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

    def create_nodes(self, reactor, names, distribution, metadata={}):
        """
        Create nodes with the given names.

        :param reactor: The reactor.
        :param name: The names of the nodes.
        :type name: list of str
        :param str distribution: The name of the distribution to
            install on the nodes.
        :param dict metadata: Metadata to associate with the nodes.

        :return: A list of ``Deferred``s each firing with an INode
            when the corresponding node is created.   The list has
            the same order as :param:`names`.

        """
        size = self._default_size
        image_name = self._image_names[distribution]
        create_node_arguments = self._create_node_arguments()

        def handle_create_error(failure, name):
            # XXX This could be dangerous... What about a pre-existing
            # node with the same name (or even multiple nodes if the name
            # does not have to be unique)?
            Message.log(
                message_type="flocker:provision:libcloud:create_node:failed",
                node_name=name,
            )
            write_failure(failure)
            d = self._async_cleanup_node_named(reactor, name)
            d.addCallback(lambda _: failure)
            return d

        def make_node(node):
            public_address = _filter_ipv4(node.public_ips)[0]
            if isinstance(public_address, unicode):
                public_address = public_address.encode("ascii")

            if self._use_private_addresses:
                private_address = _filter_ipv4(node.private_ips)[0]
            else:
                private_address = None

            if isinstance(private_address, unicode):
                private_address = private_address.encode("ascii")

            Message.log(
                message_type="flocker:provision:libcloud:node_created",
                name=node.name,
                id=node.id,
                public_address=public_address,
                private_address=private_address,
            )
            return LibcloudNode(
                provisioner=self,
                node=node, address=public_address,
                private_address=private_address,
                distribution=distribution)

        action = start_action(
            action_type=u"flocker:provision:libcloud:create_nodes",
            instance_count=len(names),
            distribution=distribution,
            size=size,
            metadata=metadata,
        )
        with action.context():
            results = []
            for name in names:
                Message.log(
                    message_type=u"flocker:provision:libcloud:creating_node",
                    node_name=name,
                )
                d = maybeDeferred(
                    self._driver.create_node,
                    name=name,
                    image=get_image(self._driver, image_name),
                    size=get_size(self._driver, size),
                    ex_keyname=self._keyname,
                    ex_metadata=metadata,
                    **create_node_arguments
                )
                d = DeferredContext(d)
                d.addCallbacks(
                    lambda node: self._wait_until_running(reactor, node),
                    errback=handle_create_error,
                    errbackArgs=(name,),
                )
                d.addCallback(make_node)
                results.append(d.result)

            action_completion = DeferredContext(DeferredList(results))
            action_completion.addActionFinish()
            # Individual results and errors should be consumed by the caller,
            # so we can leave action_completion alone now.
            return results

    def _async_cleanup_node_named(self, reactor, name):
        """
        Destroy a node with the given name, if there is one.  Otherwise, do
        nothing.
        """
        d = _retry_exception_async(reactor, self._driver.list_nodes)
        d = DeferredContext(d)

        def destroy_if_found(nodes):
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
                    return _retry_exception_async(reactor, node.destroy)

        d.addCallback(destroy_if_found)
        return d.result

    def _async_refresh_node(self, reactor, target_node):
        """
        Determine the latest state of the node.

        :param target_node: A libcloud node object representing the compute
            instance to examine.

        :return: Deferred that fires with a libcloud node object that
            has the updated information about the node if the node is found,
            ``None`` otherwise (e.g. if the node has been destroyed).
        """
        d = _retry_exception_async(reactor, self._driver.list_nodes)

        def got_nodes(nodes):
            for node in nodes:
                if node.uuid == target_node.uuid:
                    Message.log(
                        message_type=(
                            u"flocker:provision:libcloud:refresh_node"
                        ),
                        name=node.name,
                        id=node.id,
                        state=node.state,
                        public_ips=node.public_ips,
                        private_ips=node.private_ips,
                    )
                    return node
            return None

        d.addCallback(got_nodes)
        return d

    def _async_node_in_state(self, reactor, target_node, target_states):
        """
        Determine whether a compute instance is in one of the given states.

        :param target_node: A libcloud node object representing the compute
            instance to examine.
        :param set target_states: The states to compare the compute instance's
            actual state against.

        :return: Deferred that fires with ``True`` if the compute instance is
            currently in one of ``target_states``, ``False`` otherwise.
        """
        d = self._async_refresh_node(reactor, target_node)

        def check_state(node):
            if node is not None:
                if node.state in target_states:
                    Message.log(
                        message_type=(
                            u"flocker:provision:libcloud:node_in_state"
                        ),
                        name=node.name,
                        id=node.id,
                        state=node.state,
                    )
                    return True
            return False

        d.addCallback(check_state)
        return d

    def _wait_until_running(self, reactor, node):
        """
        Wait until the node is running and its network interface is configured.

        This method fails if the node does not reach the expected state until
        the predefined timeout expires or if the node goes into an error state
        or an unexpected state.

        :param node: A libcloud node object representing the compute instance
            of interest.
        :return: Deferred that fires with a libcloud node object representing
            the latest state of the instance in the case of success.
        """
        # Overall retry sleep time (not quite the same as timeout since
        # it doesn't count time spent in the predicate) is just copied
        # from the default libcloud timeout for wait_until_running.
        # Maybe some other value would be better.
        action = start_action(
            action_type=u"flocker:provision:libcloud:wait_until_running",
            name=node.name,
            id=node.id,
        )
        with action.context():
            steps = iter([15] * (600 / 15))
            d = loop_until(
                reactor,
                lambda: self._async_node_in_state(
                    reactor,
                    node,
                    self.TERMINAL_STATES
                ),
                steps=steps,
            )
            d = DeferredContext(d)

            def got_ip_addresses():
                d = self._async_refresh_node(reactor, node)
                d = DeferredContext(d)

                def is_running(updated_node):
                    if updated_node.state is not NodeState.RUNNING:
                        raise Exception("Node failed to run")
                    return updated_node

                def check_addresses(updated_node):
                    """
                    Check if the node has got at least one IPv4 public address
                    and, if requested, an IPv4 private address.  If yes, then
                    return the node object with the addresses, None otherwise.
                    """
                    public_ips = _filter_ipv4(updated_node.public_ips)
                    if len(public_ips) > 0:
                        if self._use_private_addresses:
                            private_ips = _filter_ipv4(
                                updated_node.private_ips
                            )
                            if len(private_ips) == 0:
                                return None
                        return updated_node
                    else:
                        return None

                d.addCallback(is_running)
                d.addCallback(check_addresses)
                return d.result

            # Once node is in a stable state ensure that it is running
            # and it has necessary IP addresses assigned.
            d.addCallback(
                lambda _: loop_until(reactor, got_ip_addresses, steps=steps)
            )

            def failed_to_run(failure):
                d = _retry_exception_async(reactor, node.destroy)
                d.addCallback(lambda _: failure)
                return d

            d.addErrback(failed_to_run)
            return d.addActionFinish()


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


def _retry_exception_async(reactor, f, steps=(0.1,) * 10):
    """
    Retry a function if it raises an exception.

    :return: Deferred that fires with whatever the function returns or the
        last raised exception if the function never succeeds.
    """
    # Any failure is recorded and converted to False so that loop_until keeps
    # trying.  Any success is recorded and converted to True so that
    # loop_until completes even if the result evaluates to False.
    # If loop_until() succeeds then the recorded result is returned, otherwise
    # the last recorded failure is returned.
    saved_failure = [None]
    saved_result = [None]

    def handle_success(result):
        saved_result[0] = result
        return True

    def handle_failure(failure):
        Message.log(
            message_type=(
                u"flocker:provision:libcloud:retry_exception:got_exception"
            ),
        )
        write_failure(failure)
        saved_failure[0] = failure
        return False

    def make_call():
        d = maybeDeferred(f)
        d = DeferredContext(d)
        d.addCallbacks(handle_success, errback=handle_failure)
        return d.result

    action = start_action(
        action_type=u"flocker:provision:libcloud:retry_exception",
        function=function_serializer(f),
    )
    with action.context():
        d = loop_until(reactor, make_call, steps)
        d = DeferredContext(d)
        d.addCallbacks(
            lambda _: saved_result[0],
            errback=lambda _: saved_failure[0],
        )
        return d.addActionFinish()


def _filter_ipv4(addresses):
    """
    Select IPv4 addresses from the list of IP addresses.

    :param list addresses: The list of the addresses to filter.
    :return: The list of addresses that are IPv4 addresses.
    :rtype: list
    """
    return [
        address for address in addresses
        if is_valid_ip_address(address=address, family=socket.AF_INET)
    ]
