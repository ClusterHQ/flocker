# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-deploy`` command line tool.
"""
from subprocess import check_output, CalledProcessError
from unittest import skipUnless
from os import environ
from copy import deepcopy

from yaml import safe_dump

from twisted.python.procutils import which
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from twisted.internet import reactor
from twisted.internet.utils import getProcessOutputAndValue
from twisted.web.resource import Resource
from twisted.web.server import Site

from ...testtools.ssh import create_ssh_server, create_ssh_agent
from .._sshconfig import OpenSSHConfiguration
from ...control import (
    FlockerConfiguration, model_from_configuration)

from ...control.httpapi import ConfigurationAPIUserV1
from ...control._persistence import ConfigurationPersistenceService
from ...control._clusterstate import ClusterStateService
from ...control.test.test_config import (
    COMPLEX_APPLICATION_YAML, COMPLEX_DEPLOYMENT_YAML)

from ..script import DeployScript, _OK_MESSAGE

from ... import __version__


_require_installed = skipUnless(which("flocker-deploy"),
                                "flocker-deploy not installed")


class FlockerDeployTests(TestCase):
    """
    Tests for ``flocker-deploy``.
    """
    @_require_installed
    def setUp(self):
        self.persistence_service = ConfigurationPersistenceService(
            reactor, FilePath(self.mktemp()))
        self.persistence_service.startService()
        self.cluster_state_service = ClusterStateService()
        self.cluster_state_service.startService()
        self.addCleanup(self.cluster_state_service.stopService)
        self.addCleanup(self.persistence_service.stopService)
        app = ConfigurationAPIUserV1(self.persistence_service,
                                     self.cluster_state_service).app
        api_root = Resource()
        api_root.putChild('v1', app.resource())
        self.port = reactor.listenTCP(0, Site(api_root),
                                      interface="127.0.0.1")
        self.addCleanup(self.port.stopListening)
        self.port_number = self.port.getHost().port

    def test_version(self):
        """``flocker-deploy --version`` returns the current version."""
        result = check_output([b"flocker-deploy"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))

    def _send_configuration(self,
                            application_config_yaml=COMPLEX_APPLICATION_YAML,
                            deployment_config_yaml=COMPLEX_DEPLOYMENT_YAML):
        """
        Run ``flocker-deploy`` against the API server.

        :param application_config: Application configuration dictionary.
        :param deployment_config: Deployment configuration dictionary.

        :return: ``Deferred`` that fires with a tuple (stdout, stderr,
            exit code).
        """
        app_config = FilePath(self.mktemp())
        app_config.setContent(safe_dump(application_config_yaml))
        deployment_config = FilePath(self.mktemp())
        deployment_config.setContent(safe_dump(deployment_config_yaml))
        return getProcessOutputAndValue(
            b"flocker-deploy", [
                b"--nossh",
                b"--port", unicode(self.port_number).encode("ascii"),
                b"localhost", deployment_config.path, app_config.path],
            env=environ)

    def test_configures_cluster(self):
        """
        ``flocker-deploy`` sends the configuration to the API endpoint that
        will replace the cluster configuration.
        """
        result = self._send_configuration()
        apps = FlockerConfiguration(
            deepcopy(COMPLEX_APPLICATION_YAML)).applications()
        expected = model_from_configuration(
            applications=apps,
            deployment_configuration=deepcopy(COMPLEX_DEPLOYMENT_YAML))
        result.addCallback(lambda _: self.assertEqual(
            self.persistence_service.get(), expected))
        return result

    def test_output(self):
        """
        ``flocker-deploy`` prints a helpful message when it's done.
        """
        result = self._send_configuration()
        result.addCallback(self.assertEqual, (_OK_MESSAGE, b"", 0))
        return result

    def test_error(self):
        """
        ``flocker-deploy`` exits with error code 1 and prints the returned
        error message if the API endpoint returns a non-successful
        response code.
        """
        result = self._send_configuration(
            application_config_yaml={"bogus": "bogus"})
        result.addCallback(
            self.assertEqual,
            (b"",
             b'Application configuration has an error. '
             b'Missing \'applications\' key.\n\n', 1))
        return result


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
        script = DeployScript(
            ssh_configuration=self.config, ssh_port=self.server.port)
        result = script._configure_ssh([unicode(self.server.ip)])

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

        script = DeployScript(
            ssh_configuration=self.config, ssh_port=self.server.port)
        result = script._configure_ssh([unicode(self.server.ip)])
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

        script = DeployScript(
            ssh_configuration=self.config, ssh_port=self.server.port)
        result = script._configure_ssh([unicode(self.server.ip)])
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

        script = DeployScript(
            ssh_configuration=self.config, ssh_port=self.server.port)
        result = script._configure_ssh([u'node1.example.com',
                                        u'node2.example.com',
                                        u'node3.example.com'])

        def check_logs(ignored_first_error):
            failures = self.flushLoggedErrors(ZeroDivisionError)
            # SSH configuration is performed in parallel threads so the order
            # of logged errors depends on the thread scheduling. Sort the
            # results before comparing.
            self.assertEqual(
                sorted(expected_errors),
                sorted(f.value for f in failures)
            )

        result.addErrback(check_logs)
        return result
