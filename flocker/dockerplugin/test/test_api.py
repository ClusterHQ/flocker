# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Volumes Plugin API provided by the plugin.
"""

from uuid import uuid4

from twisted.web.http import OK

from .._api import VolumePlugin
from ...apiclient import FakeFlockerClient

from ...restapi.testtools import buildIntegrationTests, APIAssertionsMixin


class APITestsMixin(APIAssertionsMixin):
    """
    Helpers for writing tests for the Docker Volume Plugin API.
    """
    NODE_A = uuid4()
    NODE_B = uuid4()

    def initialize(self):
        """
        Create initial objects for the ``VolumePlugin``.
        """
        self.flocker_client = FakeFlockerClient()

    def test_pluginactivate(self):
        """
        ``/Plugins.Activate`` indicates the plugin is a volume driver.
        """
        # Really we should be sending a blank body, but that has some
        # issues since @structured then expects a POST to have a
        # application/json content type. Fixing up the content type issues
        # (a necessary chunk of work) is covered by FLOC-2811, which
        # should also fix this.
        return self.assertResult(b"POST", b"/Plugin.Activate", {}, OK,
                                 {u"Implements": [u"VolumeDriver"]})

    def test_remove(self):
        """
        ``/VolumeDriver.Remove`` returns a successful result.
        """
        return self.assertResult(b"POST", b"/VolumeDriver.Remove",
                                 {u"Name": u"vol"}, OK, {u"Err": None})

    def test_unmount(self):
        """
        ``/VolumeDriver.Unmount`` returns a successful result.
        """
        return self.assertResult(b"POST", b"/VolumeDriver.Unmount",
                                 {u"Name": u"vol"}, OK, {u"Err": None})


def _build_app(test):
    test.initialize()
    return VolumePlugin(test.flocker_client, test.NODE_A).app
RealTestsAPI, MemoryTestsAPI = buildIntegrationTests(
    APITestsMixin, "API", _build_app)
