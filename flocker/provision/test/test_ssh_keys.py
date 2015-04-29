# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.provision._ssh._keys`.
"""

from twisted.internet import reactor
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.testtools.ssh import create_ssh_agent, generate_ssh_key

from .._ssh._keys import check_agent_has_ssh_key


class CheckKeyTests(TestCase):
    """
    """
    def test_public_key_in_agent(self):
        """
        If the running ssh-agent has the provided private key,
        assoicated to a given public key, then ``ssh_agent_has_ssh_key``
        returns ``True``.
        """
        key_file = FilePath(self.mktemp())
        key = generate_ssh_key(key_file).public()

        create_ssh_agent(key_file, self)

        result = check_agent_has_ssh_key(reactor, key)
        result.addCallback(self.assertTrue)
        return result

    def test_private_key_in_agent(self):
        key_file = FilePath(self.mktemp())
        key = generate_ssh_key(key_file)

        create_ssh_agent(key_file, self)

        result = check_agent_has_ssh_key(reactor, key)
        result.addCallback(self.assertTrue)
        return result

    def test_public_key_not_in_agent(self):
        """
        If the running ssh-agent does not have a key assoicated to the given
        public key, then ``ssh_agent_has_ssh_key`` returns ``False``.
        """
        key_file = FilePath(self.mktemp())
        generate_ssh_key(key_file)
        create_ssh_agent(key_file, self)

        other_key = generate_ssh_key(FilePath(self.mktemp())).public()

        result = check_agent_has_ssh_key(reactor, other_key)
        result.addCallback(self.assertFalse)
        return result
