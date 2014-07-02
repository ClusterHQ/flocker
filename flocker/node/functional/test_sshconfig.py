# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker._sshconfig``.
"""

from os import devnull, environ, kill
from signal import SIGKILL
from socket import socket
from subprocess import check_output, check_call

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath
from twisted.conch.ssh.keys import Key
from twisted.internet.threads import deferToThread

from .._sshconfig import _OpenSSHConfiguration
from ...testtools import create_ssh_server

def goodlines(path):
    """
    Return a list of lines read from ``path`` excluding those that are blank
    or begin with ``#``.

    :param FilePath path: The path to the file to read.

    :return: A ``list`` of ``bytes`` giving good lines from the file.
    """
    return list(line for line in path.getContent().splitlines()
                if line and not line.strip().startswith(b"#"))


class ConfigureSSHTests(TestCase):
    """
    Tests for ``configure_ssh``.
    """
    def setUp(self):
        self.ssh_config = FilePath(self.mktemp())
        self.server = create_ssh_server(self.ssh_config)
        self.addCleanup(self.server.restore)
        self.flocker_config = FilePath(self.mktemp())
        self.config = _OpenSSHConfiguration(
            ssh_config_path=self.ssh_config,
            flocker_path=self.flocker_config)
        self.configure_ssh = self.config.configure_ssh

        output = check_output([b"ssh-agent", b"-c"]).splitlines()
        self.addCleanup(lambda: kill(int(pid), SIGKILL))

        # setenv SSH_AUTH_SOCK /tmp/ssh-5EfGti8RPQbQ/agent.6390;
        # setenv SSH_AGENT_PID 6391;
        # echo Agent pid 6391;
        sock = output[0].split()[2][:-1]
        pid = output[1].split()[2][:-1]
        environ[b"SSH_AUTH_SOCK"] = sock
        environ[b"SSH_AGENT_PID"] = pid
        with open(devnull, "w") as discard:
            check_call(
                [b"ssh-add", self.server.key_path.path],
                stdout=discard, stderr=discard)

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
        configuring = deferToThread(
            self.configure_ssh, self.server.ip, self.server.port)
        def generated(ignored):
            id_rsa = self.ssh_config.child(b"id_rsa_flocker")
            id_rsa_pub = self.ssh_config.child(b"id_rsa_flocker.pub")
            key = Key.fromFile(id_rsa.path)
            self.assertEqual(
                # Avoid comparing the comment
                key.public().toString("OPENSSH").split()[:2],
                id_rsa_pub.getContent().split()[:2])
        configuring.addCallback(generated)
        return configuring

    def test_key_not_regenerated(self):
        """
        ``configure_ssh`` does not generate a new key pair if one can already
        be found in ``id_rsa_flocker`` and ``id_rsa_flocker.pub``.
        """
        id_rsa = self.ssh_config.child(b"id_rsa_flocker")

        configuring = deferToThread(
            self.configure_ssh, self.server.ip, self.server.port)
        def generated(ignored):
            key = Key.fromFile(id_rsa.path)

            configuring = deferToThread(
                self.configure_ssh, self.server.ip, self.server.port)
            configuring.addCallback(lambda ignored: key)
            return configuring
        configuring.addCallback(generated)

        def not_regenerated(expected_key):
            self.assertEqual(expected_key, Key.fromFile(id_rsa.path))
        configuring.addCallback(not_regenerated)
        return configuring

    def test_authorized_keys(self):
        """
        When the SSH connection is established, the ``~/.ssh/authorized_keys``
        file has the public part of the generated key pair appended to it.
        """
        configuring = deferToThread(self.configure_ssh, self.server.ip, self.server.port)
        def configured(ignored):
            id_rsa_pub = self.ssh_config.child(b"id_rsa_flocker.pub")
            keys = self.server.home.descendant([b".ssh", b"authorized_keys"])

            # Compare the contents ignoring comments for ease.
            self.assertEqual(goodlines(id_rsa_pub), goodlines(keys))

        configuring.addCallback(configured)
        return configuring

    def test_authorized_keys_already_in_place(self):
        """
        When the SSH connection is established, if the
        ``~/.ssh/authorized_keys`` file already has the public part of the key
        pair then it is not appended again.
        """
        configuring = deferToThread(
            self.configure_ssh, self.server.ip, self.server.port)
        configuring.addCallback(
            lambda ignored:
                deferToThread(
                    self.configure_ssh, self.server.ip, self.server.port))
        def configured(ignored):
            id_rsa_pub = self.ssh_config.child(b"id_rsa_flocker.pub")
            keys = self.server.home.descendant([b".ssh", b"authorized_keys"])
            self.assertEqual(goodlines(id_rsa_pub), goodlines(keys))
        configuring.addCallback(configured)
        return configuring

    def test_existing_authorized_keys_preserved(self):
        """
        Any unrelated content in the ``~/.ssh/authorized_keys`` file is left in
        place by ``configure_ssh``.
        """
        existing_keys = (
            b"ssh-dss AAAAB3Nz1234567890 comment\n"
            b"ssh-dss AAAAB3Nz0987654321 comment\n"
        )
        ssh_path = self.server.home.child(b".ssh")
        ssh_path.makedirs()

        authorized_keys = ssh_path.child(b"authorized_keys")
        authorized_keys.setContent(existing_keys)
        configuring = deferToThread(self.configure_ssh, self.server.ip, self.server.port)
        def configured(ignored):
            self.assertIn(existing_keys, authorized_keys.getContent())
        configuring.addCallback(configured)
        return configuring

    def test_flocker_keypair_written(self):
        """
        ``configure_ssh`` writes the keypair to ``id_rsa_flocker`` and
        ``id_rsa_flocker.pub`` remotely.
        """
        configuring = deferToThread(self.configure_ssh, self.server.ip, self.server.port)
        def configured(ignored):
            expected = (
                self.ssh_config.child(b"id_rsa_flocker").getContent(),
                self.ssh_config.child(b"id_rsa_flocker.pub").getContent()
            )
            actual = (
                self.flocker_config.child(b"id_rsa_flocker").getContent(),
                self.flocker_config.child(b"id_rsa_flocker.pub").getContent()
            )
            self.assertEqual(expected, actual)
        configuring.addCallback(configured)
        return configuring
