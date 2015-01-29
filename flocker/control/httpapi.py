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

    def __init__(self, persistence_service, cluster_state_service):
        """
        :param ConfigurationPersistenceService persistence_service: Service
            for retrieving and setting desired configuration.

        :param ClusterStateService cluster_state_service: Service that
            knows about the current state of the cluster.
        """
        self.persistence_service = persistence_service
        self.cluster_state_service = cluster_state_service

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

    # # Will we also have a /state endpoint? Or just route directly to the datasets path?
    # @app.route("/state/datasets", methods=['GET'])
    # @user_documentation("""
    #     Get current cluster datasets
    #     """, examples=[u"get state datasets"])
    # @structured(
    #     inputSchema={},
    #     outputSchema={'$ref': '/v1/endpoints.json#/definitions/state/datasets'},
    #     schema_store=SCHEMAS
    # )
    # def datasets(self):
    #     """
    #     Return all datasets in the cluster.
    #     """

def create_api_service(persistence_service, cluster_state_service, endpoint):
    """
    Create a Twisted Service that serves the API on the given endpoint.

    :param ConfigurationPersistenceService persistence_service: Service
        for retrieving and setting desired configuration.

    :param ClusterStateService cluster_state_service: Service that
        knows about the current state of the cluster.

    :param endpoint: Twisted endpoint to listen on.

    :return: Service that will listen on the endpoint using HTTP API server.
    """
    api_root = Resource()
    user = DatasetAPIUserV1(persistence_service, cluster_state_service)
    api_root.putChild('v1', user.app.resource())
    api_root._v1_user = user  # For unit testing purposes, alas
    return StreamServerEndpointService(endpoint, Site(api_root))
