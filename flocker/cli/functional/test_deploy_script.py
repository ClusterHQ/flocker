# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-deploy`` command line tool.
"""
from subprocess import check_output, CalledProcessError
from unittest import skipUnless

from twisted.python.procutils import which
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from ...testtools.ssh import create_ssh_server, create_ssh_agent
from .._sshconfig import OpenSSHConfiguration
from ...control import Deployment, Node

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
        self.agent = create_ssh_agent(self.server.key_path, self)

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

    def test_sshkey_installation_failure(self):
        """
        ``DeployScript._configure_ssh`` fires with an errback if one of the
        configuration attempts fails.
        """
        def fail(host, port):
            raise ZeroDivisionError()
        self.config.configure_ssh = fail

        deployment = Deployment(
            nodes=frozenset([
                Node(
                    hostname=str(self.server.ip),
                    applications=None
                ),
            ])
        )

        script = DeployScript(
            ssh_configuration=self.config, ssh_port=self.server.port)
        result = script._configure_ssh(deployment)
        result.addErrback(lambda f: f.value.subFailure)
        result = self.assertFailure(result, ZeroDivisionError)
        # Handle errors logged by gather_deferreds
        self.addCleanup(self.flushLoggedErrors, ZeroDivisionError)
        return result

    def test_sshkey_installation_ssh_process_failure(self):
        """
        ``DeployScript._configure_ssh`` fires with a ``SystemExit`` errback
        containing the SSH process output if one of the configuration
        attempts fails.
        """
        def fail(host, port):
            raise CalledProcessError(1, "ssh", output=b"onoes")
        self.config.configure_ssh = fail

        deployment = Deployment(
            nodes=frozenset([
                Node(
                    hostname=str(self.server.ip),
                    applications=None
                ),
            ])
        )

        script = DeployScript(
            ssh_configuration=self.config, ssh_port=self.server.port)
        result = script._configure_ssh(deployment)
        result = self.assertFailure(result, SystemExit)
        result.addCallback(lambda exc: self.assertEqual(
            exc.args, (b"Error connecting to cluster node: onoes",)))
        # Handle errors logged by gather_deferreds
        self.addCleanup(self.flushLoggedErrors, CalledProcessError)
        return result

    def test_sshkey_installation_failure_logging(self):
        """
        ``DeployScript._configure_ssh`` logs all failed configuration attempts.
        """
        expected_errors = [
            ZeroDivisionError("error1"),
            ZeroDivisionError("error2"),
            ZeroDivisionError("error3"),
        ]

        error_iterator = (e for e in expected_errors)

        def fail(host, port):
            raise error_iterator.next()

        self.config.configure_ssh = fail

        deployment = Deployment(
            nodes=frozenset([
                Node(
                    hostname=b'node1.example.com',
                    applications=None
                ),
                Node(
                    hostname=b'node2.example.com',
                    applications=None
                ),
                Node(
                    hostname=b'node3.example.com',
                    applications=None
                ),

            ])
        )

        script = DeployScript(
            ssh_configuration=self.config, ssh_port=self.server.port)
        result = script._configure_ssh(deployment)

        def check_logs(ignored_first_error):
            failures = self.flushLoggedErrors(ZeroDivisionError)
            self.assertEqual(
                expected_errors,
                [f.value for f in failures]
            )

        result.addErrback(check_logs)
        return result
