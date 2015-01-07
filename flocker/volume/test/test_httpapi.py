# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``flocker.volume.httpapi``.
"""

from zope.interface.verify import verifyObject

from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import MemoryReactor
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.web.server import Site
from twisted.web.client import readBody
from twisted.application.service import IService

from ...restapi.testtools import (
    buildIntegrationTests, loads, goodResult)

from ..httpapi import DatasetAPIUser, create_api_service


class APITestsMixin(object):
    """
    Integration tests for the Dataset Manager API.
    """
    def test_noop(self):
        """
        The ``/noop`` commands return JSON-encoded ``null``.
        """
        requesting = self.agent.request(b"GET", b"/noop")
        requesting.addCallback(readBody)
        requesting.addCallback(lambda body: self.assertEqual(
            goodResult(None), loads(body)))
        return requesting


RealTestsAPI, MemoryTestsAPI = buildIntegrationTests(
    APITestsMixin, "API", lambda test: DatasetAPIUser().app)


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
        verifyObject(IService, create_api_service(endpoint))

    def test_listens_endpoint(self):
        """
        ``create_api_service`` returns a service that listens using the given
        endpoint with a HTTP server.
        """
        reactor = MemoryReactor()
        endpoint = TCP4ServerEndpoint(reactor, 6789)
        service = create_api_service(endpoint)
        self.addCleanup(service.stopService)
        service.startService()
        server = reactor.tcpServers[0]
        port = server[0]
        factory = server[1].__class__
        self.assertEqual((port, factory), (6789, Site))
