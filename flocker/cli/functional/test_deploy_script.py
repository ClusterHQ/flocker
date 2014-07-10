# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-deploy`` command line tool.
"""
from subprocess import check_output
from unittest import skipUnless

from twisted.python.procutils import which
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from ...testtools import create_ssh_server, create_ssh_agent
from .._sshconfig import OpenSSHConfiguration
from ...node import Deployment, Node

from ..script import DeployScript

from ... import __version__


_require_installed = skipUnless(which("flocker-deploy"),
                                "flocker-deploy not installed")


class FlockerDeployTests(TestCase):
    """
    Tests for ``flocker-deploy``.
    """
    @_require_installed
    def setUp(self):
        pass

    def test_version(self):
        """``flocker-deploy --version`` returns the current version."""
        result = check_output([b"flocker-deploy"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))


class FlockerDeployConfigureSSHTests(TestCase):
    """
    Tests for ``DeployScript._configure_ssh``.
    """

    @_require_installed
    def setUp(self):
        self.sshd_config = FilePath(self.mktemp())
        self.server = create_ssh_server(self.sshd_config)
        self.addCleanup(self.server.restore)
        self.flocker_config = FilePath(self.mktemp())
        self.local_user_ssh = FilePath(self.mktemp())

        self.config = OpenSSHConfiguration(
            ssh_config_path=self.local_user_ssh,
            flocker_path=self.flocker_config)
        self.configure_ssh = self.config.configure_ssh

        # ``configure_ssh`` expects ``ssh`` to already be able to
        # authenticate against the server.  Set up an ssh-agent to
        # help it do that against our testing server.
        self.agent = create_ssh_agent(self.server.key_path)

        self.addCleanup(self.agent.restore)

    def test_installs_public_sshkeys(self):
        """
        ``DeployScript._configure_ssh`` installs the cluster wide public ssh
        keys on each node in the supplied ``Deployment``.
        """
        deployment = Deployment(
            nodes=frozenset([
                Node(
                    hostname=str(self.server.ip),
                    applications=None
                ),
                # Node(
                #     hostname='node2.example.com',
                #     applications=None
                # )
            ])
        )

        script = DeployScript(
            ssh_configuration=self.config, ssh_port=self.server.port)
        result = script._configure_ssh(deployment)

        local_key = self.local_user_ssh.child(b'id_rsa_flocker.pub')
        authorized_keys = self.sshd_config.descendant([
            b'home', b'.ssh', b'authorized_keys'])

        def check_authorized_keys(ignored):
            self.assertIn(local_key.getContent().rstrip(),
                          authorized_keys.getContent().splitlines())

        result.addCallback(check_authorized_keys)
        return result
