# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.cli._sshconfig``.
"""

from os.path import expanduser
from socket import socket

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath, Permissions
from twisted.conch.ssh.keys import Key
from twisted.internet.threads import deferToThread

from .. import configure_ssh
from .._sshconfig import OpenSSHConfiguration
from ...testtools import create_ssh_server, create_ssh_agent


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
        # Create a fake local keypair
        # Must come after `create_ssh_server` since that will create the parent
        # directory for us.
        self.ssh_config.child(b"id_rsa_flocker").setContent('private key\n')
        self.ssh_config.child(b"id_rsa_flocker.pub").setContent('public key\n')
        self.addCleanup(self.server.restore)
        self.flocker_config = FilePath(self.mktemp())
        self.config = OpenSSHConfiguration(
            ssh_config_path=self.ssh_config,
            flocker_path=self.flocker_config)
        self.configure_ssh = self.config.configure_ssh
        self.agent = create_ssh_agent(self.server.key_path)

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

    def test_authorized_keys(self):
        """
        When the SSH connection is established, the ``~/.ssh/authorized_keys``
        file has the public part of the generated key pair appended to it.
        """
        configuring = deferToThread(
            self.configure_ssh, self.server.ip, self.server.port)

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
        configuring = deferToThread(
            self.configure_ssh, self.server.ip, self.server.port)

        def configured(ignored):
            self.assertIn(existing_keys, authorized_keys.getContent())
        configuring.addCallback(configured)
        return configuring

    def test_flocker_keypair_written(self):
        """
        ``configure_ssh`` writes the keypair to ``id_rsa_flocker`` and
        ``id_rsa_flocker.pub`` remotely.
        """
        configuring = deferToThread(
            self.configure_ssh, self.server.ip, self.server.port)

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


    def test_flocker_keypair_permissions(self):
        """
        ``configure_ssh`` writes the remote keypair with secure permissions.
        """
        configuring = deferToThread(
            self.configure_ssh, self.server.ip, self.server.port)

        expected_private_key_permissions = Permissions(0600)
        expected_public_key_permissions = Permissions(0644)

        def configured(ignored):
            expected = (
                expected_private_key_permissions,
                expected_public_key_permissions
            )
            actual = (
                self.flocker_config.child(b"id_rsa_flocker").getPermissions(),
                self.flocker_config.child(b"id_rsa_flocker.pub").getPermissions()
            )
            self.assertEqual(expected, actual)
        configuring.addCallback(configured)
        return configuring


class CreateKeyPairTests(TestCase):
    """
    Tests for ``create_keypair``.
    """
    def test_key_generated(self):
        """
        ``create_keypair`` generates a new key pair and writes it locally to
        ``id_rsa_flocker`` and ``id_rsa_flocker.pub``.
        """
        ssh_config = FilePath(self.mktemp())
        configurator = OpenSSHConfiguration(
            ssh_config_path=ssh_config, flocker_path=None)

        configuring = deferToThread(configurator.create_keypair)

        def generated(ignored):
            id_rsa = ssh_config.child(b"id_rsa_flocker")
            id_rsa_pub = ssh_config.child(b"id_rsa_flocker.pub")
            key = Key.fromFile(id_rsa.path)
            self.assertEqual(
                # Avoid comparing the comment
                key.public().toString("OPENSSH").split()[:2],
                id_rsa_pub.getContent().split()[:2])
        configuring.addCallback(generated)
        return configuring

    def test_key_not_regenerated(self):
        """
        ``create_keypair`` does not generate a new key pair if one can
        already be found in ``id_rsa_flocker`` and ``id_rsa_flocker.pub``.
        """
        ssh_config = FilePath(self.mktemp())
        configurator = OpenSSHConfiguration(
            ssh_config_path=ssh_config, flocker_path=None)

        id_rsa = ssh_config.child(b"id_rsa_flocker")

        configuring = deferToThread(configurator.create_keypair)

        def generated(ignored):
            key = Key.fromFile(id_rsa.path)

            configuring = deferToThread(configurator.create_keypair)
            configuring.addCallback(lambda ignored: key)
            return configuring
        configuring.addCallback(generated)

        def not_regenerated(expected_key):
            self.assertEqual(expected_key, Key.fromFile(id_rsa.path))
        configuring.addCallback(not_regenerated)
        return configuring

    def test_key_permissions(self):
        """
        ``create_keypair`` sets secure permissions on
        ``id_rsa_flocker`` and ``id_rsa_flocker.pub``.
        """
        ssh_config = FilePath(self.mktemp())
        configurator = OpenSSHConfiguration(
            ssh_config_path=ssh_config, flocker_path=None)

        configuring = deferToThread(configurator.create_keypair)

        expected_private_key_permissions = Permissions(0600)
        expected_public_key_permissions = Permissions(0644)

        def generated(ignored):
            id_rsa = ssh_config.child(b"id_rsa_flocker")
            id_rsa_pub = ssh_config.child(b"id_rsa_flocker.pub")
            self.assertEqual(
                (expected_private_key_permissions,
                 expected_public_key_permissions),
                (id_rsa.getPermissions(), id_rsa_pub.getPermissions()))
        configuring.addCallback(generated)
        return configuring


class OpenSSHDefaultsTests(TestCase):
    """
    Tests for `OpenSSHConfiguration.defaults``.
    """
    def test_flocker_path(self):
        """
        ``OpenSSHConfiguration.defaults`` creates an instance with
        ``/etc/flocker`` as the Flocker configuration path.
        """
        self.assertEqual(
            FilePath(b"/etc/flocker"),
            OpenSSHConfiguration.defaults().flocker_path)

    def test_ssh_config_path(self):
        """
        ``OpenSSHConfiguration.defaults`` creates an instance with the current
        user's SSH configuration path as the SSH configuration path.
        """
        expected = FilePath(expanduser(b"~")).child(b".ssh")
        self.assertEqual(
            expected, OpenSSHConfiguration.defaults().ssh_config_path)

    def test_configure_ssh(self):
        """
        ``configure_ssh`` is taken from an ``OpenSSHConfiguration`` instance
        created using the ``defaults`` method.
        """
        self.assertEqual(
            OpenSSHConfiguration.defaults().configure_ssh, configure_ssh)
