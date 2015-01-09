# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Dataset Manager.
"""

from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.application.internet import StreamServerEndpointService

from klein import Klein

from ..restapi import structured
from .. import __version__

class DatasetAPIUserV1(object):
    """
    A user accessing the API.
    """
    app = Klein()

    @app.route("/version")
    @structured(
        inputSchema={},
        outputSchema={'$ref': '/v1/endpoints.json#/definitions/versions'},
    )
    def version(self, request):
        """
        Do nothing.
        """
        return {"flocker": __version__}


def create_api_service(endpoint):
    """
    Create a Twisted Service that serves the API on the given endpoint.
    """
    # FLOC-1162 should add an API version prefix and integration with
    # DatasetAPIUser.
    api_root = Resource()
    api_root.putChild('v1', DatasetAPIUserV1().app.resource())
    return StreamServerEndpointService(endpoint, Site(api_root))
