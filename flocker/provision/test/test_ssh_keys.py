# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.provision._ssh._keys`.
"""

import os

from twisted.internet import reactor
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.testtools.ssh import create_ssh_agent, generate_ssh_key

from .._ssh._keys import ensure_agent_has_ssh_key, KeyNotFound, AgentNotFound


class EnsureKeyTests(TestCase):
    """
    Tests for ``ensure_agent_has_ssh_key``.
    """
    def test_public_key_in_agent(self):
        """
        If the running ssh-agent has the private key, assoicated to the
        provided public key, then ``ssh_agent_has_ssh_key`` returns a succesful
        deferred.
        """
        key_file = FilePath(self.mktemp())
        key = generate_ssh_key(key_file).public()

        create_ssh_agent(key_file, self)

        result = ensure_agent_has_ssh_key(reactor, key)
        # No assertion, since the deferred should fire with a
        # succesful result.
        return result

    def test_private_key_in_agent(self):
        """
        If the running ssh-agent has the provided private key, then
        ``ssh_agent_has_ssh_key`` returns a succesful deferred.
        """
        key_file = FilePath(self.mktemp())
        key = generate_ssh_key(key_file)

        create_ssh_agent(key_file, self)

        result = ensure_agent_has_ssh_key(reactor, key)
        # No assertion, since the deferred should fire with a
        # succesful result.
        return result

    def test_public_key_not_in_agent(self):
        """
        If the running ssh-agent does not have a key assoicated to the given
        public key, then ``ssh_agent_has_ssh_key`` returns ``False``.
        a deferred that fails with ``KeyNotFound``.
        """
        key_file = FilePath(self.mktemp())
        generate_ssh_key(key_file)
        create_ssh_agent(key_file, self)

        other_key = generate_ssh_key(FilePath(self.mktemp())).public()

        result = ensure_agent_has_ssh_key(reactor, other_key)
        return self.assertFailure(result, KeyNotFound)

    def test_agent_not_found(self):
        """
        If there is not a running ssh-agent, ``ssh_agent_has_ssh_key returns
        a deferred that fails with ``AgentNotFound``.
        """
        try:
            old_agent_socket = os.environ['SSH_AUTH_SOCK']
            self.addCleanup(os.environ.__setitem__,
                            'SSH_AUTH_SOCK', old_agent_socket)
            del os.environ['SSH_AUTH_SOCK']
        except KeyError:
            # SSH_AUTH_SOCK wasn't set, so no need to restore it.
            pass

        key_file = FilePath(self.mktemp())
        key = generate_ssh_key(key_file)
        return self.assertFailure(
            ensure_agent_has_ssh_key(reactor, key),
            AgentNotFound)
