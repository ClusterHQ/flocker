# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Dataset Manager.
"""

from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.application.service import StreamServerEndpointService

from klein import Klein

from ..restapi import structured


class DatasetAPIUser(object):
    """
    A user accessing the API.
    """
    app = Klein()

    @app.route("/noop")
    @structured({}, {})
    def noop(self):
        """
        Do nothing.
        """
        return None


def create_api_service(endpoint):
    """
    Create a Twisted Service that serves the API on the given endpoint.
    """
    # FLOC-1162 should add an API version prefix and integration with
    # DatasetAPIUser.
    return StreamServerEndpointService(endpoint, Site(Resource()))
