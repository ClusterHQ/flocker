# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.provision.test.test_ssh_keys -*-

"""
Tools for dealing with ssh keys.
"""

import os

from characteristic import attributes, Attribute

from eliot import start_action, Message
from eliot.twisted import DeferredContext

from twisted.internet.defer import fail
from twisted.internet.endpoints import UNIXClientEndpoint, connectProtocol
from twisted.conch.ssh.agent import SSHAgentClient
from twisted.conch.ssh.keys import Key


class AgentNotFound(Exception):
    """
    Raised if there is not a running ssh-agent.
    """


@attributes([
    Attribute("expected_key", instance_of=Key),
], apply_immutable=True)
class KeyNotFound(Exception):
    """
    Raised if the given key is not in the running ssh-agent.
    """
    def __str__(self):
        return "Expected key fingerprint: {}".format(
            self.expected_key.fingerprint())


def ensure_agent_has_ssh_key(reactor, key):
    """
    Check that the running ssh-agent has the private key corresponding to the
    provided key.

    :param reactor: The reactor to use to connect to the agent.
    :param Key key: The ssh key to check for in the agent.

    :return Deferred: That fires with a successful result if the key is found.
       Otherwise, fails with ``AgentNotFound`` or ``KeyNotFound``.
    """
    try:
        agent_socket = os.environ["SSH_AUTH_SOCK"]
    except KeyError:
        return fail(AgentNotFound())

    if not key.isPublic():
        key = key.public()

    action = start_action(
        action_type="flocker.provision.ssh:check_agent_has_ssh_keys",
        key_fingerprint=key.fingerprint(),
        agent_socket=agent_socket)

    with action.context():

        agent_endpoint = UNIXClientEndpoint(reactor, agent_socket)
        agent_protocol = SSHAgentClient()
        connected = DeferredContext(
            connectProtocol(agent_endpoint, agent_protocol))
        connected.addCallback(lambda _: agent_protocol.requestIdentities())

        def check_keys(results):
            for key_data, comment in results:
                agent_key = Key.fromString(key_data, type='blob')
                Message.new(
                    message_type="flocker.provision.ssh:agent_key",
                    key_fingerprint=agent_key.fingerprint(),
                    commnet=comment).write()
                if agent_key == key:
                    return True
            raise KeyNotFound(expected_key=key)
        connected.addCallback(check_keys)

        def disconnect(result):
            agent_protocol.transport.loseConnection()
            return result
        connected.addBoth(disconnect)

        return connected.addActionFinish()
