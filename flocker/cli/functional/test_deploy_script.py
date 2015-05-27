# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-deploy`` command line tool.
"""
from subprocess import check_output
from unittest import skipUnless
from os import environ
from copy import deepcopy
from uuid import uuid4

from yaml import safe_dump

from twisted.python.procutils import which
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from twisted.internet import reactor
from twisted.internet.utils import getProcessOutputAndValue
from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet.ssl import DefaultOpenSSLContextFactory

from ...control import (
    FlockerConfiguration, model_from_configuration, NodeState)

from ...control.httpapi import ConfigurationAPIUserV1
from ...control._persistence import ConfigurationPersistenceService
from ...control._clusterstate import ClusterStateService
from ...control.test.test_config import (
    COMPLEX_APPLICATION_YAML, COMPLEX_DEPLOYMENT_YAML)

from ...ca.testtools import get_credential_sets

from ..script import _OK_MESSAGE

from ... import __version__


_require_installed = skipUnless(which("flocker-deploy"),
                                "flocker-deploy not installed")


class FlockerDeployTests(TestCase):
    """
    Tests for ``flocker-deploy``.
    """
    @_require_installed
    def setUp(self):
        ca_set, _ = get_credential_sets()
        self.certificate_path = FilePath(self.mktemp())
        self.certificate_path.makedirs()
        ca_set.copy_to(self.certificate_path, user=True)

        self.persistence_service = ConfigurationPersistenceService(
            reactor, FilePath(self.mktemp()))
        self.persistence_service.startService()
        self.cluster_state_service = ClusterStateService(reactor)
        self.cluster_state_service.startService()
        self.cluster_state_service.apply_changes(
            [NodeState(uuid=uuid4(), hostname=ip)
             for ip in COMPLEX_DEPLOYMENT_YAML[u"nodes"].keys()])
        self.addCleanup(self.cluster_state_service.stopService)
        self.addCleanup(self.persistence_service.stopService)
        app = ConfigurationAPIUserV1(self.persistence_service,
                                     self.cluster_state_service).app
        api_root = Resource()
        api_root.putChild('v1', app.resource())
        # Simplest possible TLS context that presents correct control
        # service certificate; no need to validate flocker-deploy here.
        self.port = reactor.listenSSL(
            0, Site(api_root), DefaultOpenSSLContextFactory(
                ca_set.path.child(b"control-127.0.0.1.key").path,
                ca_set.path.child(b"control-127.0.0.1.crt").path),
            interface="127.0.0.1"
        )
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
        # This duplicates some code in the acceptance tests...
        # https://clusterhq.atlassian.net/browse/FLOC-1904
        return getProcessOutputAndValue(
            b"flocker-deploy", [
                b"--certificates-directory", self.certificate_path.path,
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
            deployment_state=self.cluster_state_service.as_deployment(),
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
