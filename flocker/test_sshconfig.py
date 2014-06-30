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
        ``configure_ssh`` generates a new key pair and writes it locally to
        ``id_rsa_flocker`` and ``id_rsa_flocker.pub``.
        """
        try:
            self.configure_ssh(self.server.host, self.server.port)
        except Exception:
            pass
        id_rsa = self.ssh_config.child(b"id_rsa_flocker")
        id_rsa_pub = self.ssh_config.child(b"id_rsa_flocker.pub")
        key = Key.fromFile(id_rsa.path)
        self.assertEqual(
            # Avoid comparing the comment
            key.public().toString("OPENSSH").split()[:2],
            id_rsa_pub.getContent().split()[:2])

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

    def test_authorized_keys_already_in_place(self):
        """
        When the SSH connection is established, if the
        ``~/.ssh/authorized_keys`` file already has the public part of the key
        pair then it is not appended again.
        """
        self.configure_ssh(self.server.host, self.server.port)
        self.configure_ssh(self.server.host, self.server.port)
        id_rsa_pub = self.ssh_config.child(b"id_rsa_flocker.pub")
        keys = self.server.home.descendant([b".ssh", b"authorized_keys"])
        self.assertEqual(id_rsa_pub.getContent(), keys.getContent())

    def test_existing_authorized_keys_preserved(self):
        """
        Any unrelated content in the ``~/.ssh/authorized_keys`` file is left in
        place by ``configure_ssh``.
        """
        existing_keys = (
            b"ssh-dss AAAAB3Nz1234567890 comment\n"
            b"ssh-dss AAAAB3Nz0987654321 comment\n"
        )
        authorized_keys = self.server.home.descendant([b".ssh", b"authorized_keys"])
        authorized_keys.setContent(existing_keys)
        self.configure_ssh(self.server.host, self.server.port)
        self.assertIn(existing_keys, authorized_keys.getContent())

    def test_flocker_keypair_written(self):
        """
        ``configure_ssh`` writes the keypair to ``id_rsa_flocker`` and
        ``id_rsa_flocker.pub`` remotely.
        """
        self.configure_ssh(self.server.host, self.server.port)
        expected = (
            self.ssh_config.child(b"id_rsa_flocker").getContent(),
            self.ssh_config.child(b"id_rsa_flocker.pub").getContent()
        )
        actual = (
            self.flocker_config.child(b"id_rsa_flocker").getContent(),
            self.flocker_config.child(b"id_rsa_flocker.pub").getContent()
        )
        self.assertEqual(expected, actual)
