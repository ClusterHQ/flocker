"""
Tests for ``flocker.volume.api``.
"""

from ...restapi.test.utils import (
    buildIntegrationTests, readBody, loads, goodResult)

from ..api import VolumeAPIUser


class APITestsMixin(object):
    """
    Integration tests for the Volume Manager API.
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
    APITestsMixin, "API", lambda test: VolumeAPIUser().app)
