.. _api:

========================
Flocker REST API Details
========================

.. contents::
	:local:

Introduction
============

In general the API allows for modifying the desired configuration of the cluster.
When you use the API to change the configuration, e.g. creating a new dataset:

You will need to provide API end users with a certificate for authentication before they can use the API.
For more information, see the :ref:`API authentication guide <authenticate>`.

#. A successful response indicates a change in configuration, not a change to cluster state.
#. Convergence agents will then take the necessary actions and eventually the cluster's state will match the requested configuration.
#. The actual cluster state will then reflect the requested change.
   For example, getting the current cluster datasets can be accessed via :http:get:`/v1/state/datasets`.   

.. XXX: Document the response when input validation fails:
.. https://clusterhq.atlassian.net/browse/FLOC-1613

For more information read the :ref:`cluster architecture<architecture>` documentation.

REST API Endpoints
==================

Get the cluster's container configuration
*****************************************

.. code-block:: api

	GET /v1/configuration/containers
	
These containers may or may not actually exist on the cluster.

Example: Get a list of all containers that have been configured for a deployment. 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Request

.. code-block:: json

  GET /v1/configuration/containers HTTP/1.1
  Host: api.example.com
  Content-Type: application/json
  
Response

.. code-block:: json

  HTTP/1.0 200 OK
  Content-Type: application/json
  
  [
    {
      "node_uuid": "cf0f0346-17b2-4812-beca-1434997d6c3f",
      "name": "webserver",
      "image": "nginx:latest",
      "restart_policy": {"name": "never"}
    },
    {
      "node_uuid": "7ec3c4eb-6b1c-43da-8015-a163f7d15244",
      "name": "webserver2",
      "image": "nginx:latest",
      "volumes": [{"dataset_id": "886ed03a-5606-453a-94a9-a1cbaf35164c",
                   "mountpoint": "/usr/share/nginx/html"}],
      "restart_policy": {"name": "never"}
    }
  ]



.. .. autoklein:: flocker.control.httpapi.ConfigurationAPIUserV1
    :schema_store_fqpn: flocker.control.httpapi.SCHEMAS
    :prefix: /v1
    :examples_path: api_examples.yml
