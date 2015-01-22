# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``flocker.control.httpapi``.
"""

from zope.interface.verify import verifyObject

from twisted.internet import reactor
from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import MemoryReactor
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.web.server import Site
from twisted.web.client import readBody
from twisted.application.service import IService
from twisted.python.filepath import FilePath

from ...restapi.testtools import (
    buildIntegrationTests, loads, goodResult)

from ..httpapi import DatasetAPIUserV1, create_api_service
from .._persistence import ConfigurationPersistenceService
from ... import __version__


class APITestsMixin(object):
    """
    Integration tests for the Dataset Manager API.
    """
    def initialize(self):
        """
        Create initial objects for the ``DatasetAPIUserV1``.
        """
        self.persistence_service = ConfigurationPersistenceService(
            reactor, FilePath(self.mktemp()))
        self.persistence_service.startService()
        self.addCleanup(self.persistence_service.stopService)

    def assertGoodResult(self, method, path, expected_good_result):
        """
        Assert a particular JSON response for the given API request.

        :param bytes method: HTTP method to request.
        :param bytes path: HTTP path.
        :param unicode expected_good_result: Successful good result we expect.

        :return Deferred: Fires when test is done.
        """
        requesting = self.agent.request(method, path)
        requesting.addCallback(readBody)
        requesting.addCallback(lambda body: self.assertEqual(
            goodResult(expected_good_result), loads(body)))
        return requesting

    def test_version(self):
        """
        The ``/version`` command returns JSON-encoded ``__version__``.
        """
        return self.assertGoodResult(b"GET", b"/version",
                                     {u'flocker': __version__})


def _build_app(test):
    test.initialize()
    return DatasetAPIUserV1(test.persistence_service).app
RealTestsAPI, MemoryTestsAPI = buildIntegrationTests(
    APITestsMixin, "API", _build_app)


class CreateAPIServiceTests(SynchronousTestCase):
    """
    Tests for ``create_api_service``.
    """
    def test_returns_service(self):
        """
        ``create_api_service`` returns an object providing ``IService``.
        """
        reactor = MemoryReactor()
        endpoint = TCP4ServerEndpoint(reactor, 6789)
        verifyObject(IService, create_api_service(None, endpoint))

    def test_listens_endpoint(self):
        """
        ``create_api_service`` returns a service that listens using the given
        endpoint with a HTTP server.
        """
        reactor = MemoryReactor()
        endpoint = TCP4ServerEndpoint(reactor, 6789)
        service = create_api_service(None, endpoint)
        self.addCleanup(service.stopService)
        service.startService()
        server = reactor.tcpServers[0]
        port = server[0]
        factory = server[1].__class__
        self.assertEqual((port, factory), (6789, Site))
