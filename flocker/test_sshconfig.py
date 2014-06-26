# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker._sshconfig``.
"""

from socket import socket

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.conch.ssh.keys import Key

from ._sshconfig import _OpenSSHConfiguration

class ConchServer(object):
    host = b"127.0.0.1"
    port = 12345


class ConfigureSSHTests(SynchronousTestCase):
    """
    Tests for ``configure_ssh``.
    """
    def setUp(self):
        self.server = ConchServer()
        self.ssh_config = FilePath(self.mktemp())
        self.flocker_config = FilePath(self.mktemp())
        self.config = _OpenSSHConfiguration(
            ssh_config_path=self.ssh_config,
            flocker_path=self.flocker_config)
        self.configure_ssh = self.config.configure_ssh

    def test_connection_failed(self):
        """
        If an SSH connection cannot be established to the given address then an
        exception is raised explaining that this is so.
        """
        # Bind a port and guarantee it is not accepting connections.
        blocker = socket()
        blocker.bind((b"127.0.0.1", 0))
        port = blocker.getsockname()[1]

        self.assertRaises(Exception, self.configure_ssh, b"127.0.0.1", port)

    def test_key_generated(self):
        """
        ``configure_ssh`` generates a new key pair and writes it to
        ``id_rsa_flocker`` and ``id_rsa_flocker.pub``.
        """
        try:
            self.configure_ssh(self.server.host, self.server.port)
        except Exception:
            pass
        id_rsa = self.ssh_config.child(b"id_rsa_flocker")
        id_rsa_pub = self.ssh_config.child(b"id_rsa_flocker.pub")
        key = Key.fromFile(id_rsa.path)
        self.assertEqual(key.public().toString(), id_rsa_pub.getContent())

    def test_key_not_regenerated(self):
        """
        ``configure_ssh`` does not generate a new key pair if one can already
        be found in ``id_rsa_flocker`` and ``id_rsa_flocker.pub``.
        """
        try:
            self.configure_ssh(self.server.host, self.server.port)
        except Exception:
            pass
        id_rsa = self.ssh_config.child(b"id_rsa_flocker")
        key = Key.fromFile(id_rsa.path)

        try:
            self.configure_ssh(self.server.host, self.server.port)
        except Exception:
            pass

        self.assertEqual(key, Key.fromFile(id_rsa.path))

    def test_authorized_keys(self):
        """
        When the SSH connection is established, the ``~/.ssh/authorized_keys``
        file has the public part of the generated key pair appended to it.
        """
        self.configure_ssh(self.server.host, self.server.port)
        id_rsa_pub = self.ssh_config.child(b"id_rsa_flocker.pub")
        keys = self.server.home.descendant([b".ssh", b"authorized_keys"])
        self.assertEqual(id_rsa_pub.getContent(), keys.getContent())
