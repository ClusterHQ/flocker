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
   For example, you can retrieve the current cluster datasets via :http:get:`/v1/state/datasets`.

.. XXX: Document the response when input validation fails:
.. https://clusterhq.atlassian.net/browse/FLOC-1613

For more information read the :ref:`cluster architecture<architecture>` documentation.

REST API Endpoints
==================


Common API Endpoints
--------------------

.. autoklein:: flocker.control.httpapi.ConfigurationAPIUserV1
    :schema_store_fqpn: flocker.control.httpapi.SCHEMAS
    :prefix: /v1
    :examples_path: api_examples.yml
    :section: common

Dataset API Endpoints
---------------------

.. autoklein:: flocker.control.httpapi.ConfigurationAPIUserV1
    :schema_store_fqpn: flocker.control.httpapi.SCHEMAS
    :prefix: /v1
    :examples_path: api_examples.yml
    :section: dataset


Container API Endpoints
-----------------------

.. autoklein:: flocker.control.httpapi.ConfigurationAPIUserV1
    :schema_store_fqpn: flocker.control.httpapi.SCHEMAS
    :prefix: /v1
    :examples_path: api_examples.yml
    :section: container


.. XXX: Improvements to the API (create collapse directive) requires Engineering effort:
.. https://clusterhq.atlassian.net/browse/FLOC-2094
