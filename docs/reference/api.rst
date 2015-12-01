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
For more information, see the :ref:`API authentication guide <generate-api>`.

#. A successful response indicates a change in configuration, not a change to cluster state.
#. Convergence agents will then take the necessary actions and eventually the cluster's state will match the requested configuration.
#. The actual cluster state will then reflect the requested change.
   For example, you can retrieve the current cluster datasets via :http:get:`/v1/state/datasets`.

.. XXX: Document the response when input validation fails:
.. https://clusterhq.atlassian.net/browse/FLOC-1613

For more information read the :ref:`cluster architecture<architecture>` documentation.


Using the API
=============

Conditional requests
--------------------
When using the API to create, delete or otherwise modify datasets you may wish to do so only if certain conditions apply.
For example, the Docker plugin relies on a metadata field called ``name`` to locate which dataset to use.
The ``name`` needs to be unique across all datasets.
To ensure uniqueness when creating a dataset called "my-db" we could do the following:

1. List the datasets in the configuration.
2. If "my-db" does not appear as the name of a dataset, create a new dataset.

Unfortunately this suffers from a race condition: someone else may create a dataset with name "my-db" in between steps 1 and 2.

The solution is a conditional request mechanism allowing you to say "only do this change if the configuration hasn't changed since the last time I used it."
The :http:get:`/v1/configuration/datasets` end point returns an HTTP header ``X-Configuration-Tag`` whose contents identify a particular version of the configuration::

  X-Configuration-Tag: abcdef1234

Operations that modify the configuration can then include a ``X-If-Configuration-Matches`` header with that tag as its contents::

  X-If-Configuration-Matches: abcdef1234

* If the configuration hasn't changed in the interim then the operation will succeed.
* If the configuration has changed then the operation will fail with a 412 (Precondition Failed) response code.
  In this case you would retrieve the configuration again and decide whether to retry or if the operation is no longer relevant.


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


.. XXX: Document the Python ``FlockerClient`` API.
.. https://clusterhq.atlassian.net/browse/FLOC-3306
