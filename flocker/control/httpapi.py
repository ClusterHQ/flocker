# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Dataset Manager.
"""

import yaml
from uuid import uuid4

from twisted.python.filepath import FilePath
from twisted.web.http import CONFLICT
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.application.internet import StreamServerEndpointService

from klein import Klein

from ..restapi import structured, user_documentation, make_bad_request
from .. import __version__


SCHEMA_BASE = FilePath(__file__).parent().child(b'schema')
SCHEMAS = {
    b'/v1/types.json': yaml.safe_load(
        SCHEMA_BASE.child(b'types.yml').getContent()),
    b'/v1/endpoints.json': yaml.safe_load(
        SCHEMA_BASE.child(b'endpoints.yml').getContent()),
    }


DATASET_ID_COLLISION = make_bad_request(
    code=CONFLICT, description=u"The provided dataset_id is already in use.")


class DatasetAPIUserV1(object):
    """
    A user accessing the API.
    """
    app = Klein()

    def __init__(self, persistence_service):
        """
        :param ConfigurationPersistenceService persistence_service: Service
            for retrieving and setting desired configuration.
        """
        self.persistence_service = persistence_service

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


    @app.route("/datasets", methods=['POST'])
    @user_documentation("""
        Create a new dataset.
        """, examples=[
            u"create dataset",
            u"create dataset with dataset_id",
            u"create dataset with duplicate dataset_id",
            u"create dataset with maximum_size",
            u"create dataset with metadata",
        ])
    @structured(
        inputSchema={'$ref': '/v1/endpoints.json#/definitions/datasets'},
        outputSchema={'$ref': '/v1/endpoints.json#/definitions/datasets'},
        schema_store=SCHEMAS
    )
    def create_dataset(self, primary, dataset_id=None):
        """
        Create a new dataset on the cluster.
        """
        if dataset_id is None:
            dataset_id = u"x" * 36 # unicode(uuid4())

        # Use persistence_service to get a Deployment for the cluster
        # configuration.
        deployment = self.persistence_service.get()
        for node in deployment.nodes:
            for manifestation in node.manifestations():
                if manifestation.dataset.dataset_id == dataset_id:
                    raise DATASET_ID_COLLISION

        #
        # Create a new Dataset with given parameters (generate dataset_id if
        # necessary).
        #
        # Create a new Manifestation with that Dataset.
        #
        # Add the new Manifestation to a Node in the Deployment
        # (other_manifestations) (need to merge FLOC-1214 for this).
        #
        # Persist the new Deployment using persistence_service.
        #
        # Return information about the new Manifestation???  But this is
        # create_dataset.  I guess we'll squish information from the
        # manifestation (eg the address of the primary) into the representation
        # of the dataset.
        return {
            u"dataset_id": dataset_id,
            u"primary": primary,
            u"metadata": {},
        }



def create_api_service(persistence_service, endpoint):
    """
    Create a Twisted Service that serves the API on the given endpoint.

    :param ConfigurationPersistenceService persistence_service: Service
        for retrieving and setting desired configuration.
    :param endpoint: Twisted endpoint to listen on.

    :return: Service that will listen on the endpoint using HTTP API server.
    """
    api_root = Resource()
    api_root.putChild(
        'v1', DatasetAPIUserV1(persistence_service).app.resource())
    return StreamServerEndpointService(endpoint, Site(api_root))
