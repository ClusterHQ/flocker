# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Dataset Manager.
"""

import yaml

from twisted.python.filepath import FilePath
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.application.internet import StreamServerEndpointService

from klein import Klein

from ..restapi import structured, user_documentation
from .. import __version__


SCHEMA_BASE = FilePath(__file__).parent().child(b'schema')
SCHEMAS = {
    b'/v1/types.json': yaml.safe_load(
        SCHEMA_BASE.child(b'types.yml').getContent()),
    b'/v1/endpoints.json': yaml.safe_load(
        SCHEMA_BASE.child(b'endpoints.yml').getContent()),
    }


class DatasetAPIUserV1(object):
    """
    A user accessing the API.
    """
    app = Klein()

    @app.route("/version", methods=['GET'])
    @user_documentation("""
        Get the version of Flocker being run.
        """, examples=[u"get version"])
    @structured(
        inputSchema={},
        outputSchema={'$ref': '/v1/endpoints.json#/definitions/versions'},
        schema_store=SCHEMAS
    )
    def version(self):
        """
        Return the ``flocker`` version string.
        """
        return {u"flocker":  __version__}


def create_api_service(endpoint):
    """
    Create a Twisted Service that serves the API on the given endpoint.
    """
    api_root = Resource()
    api_root.putChild('v1', DatasetAPIUserV1().app.resource())
    return StreamServerEndpointService(endpoint, Site(api_root))
