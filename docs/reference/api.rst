==================
REST API Endpoints
==================

.. _conditional requests:

Conditional requests
====================
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


Endpoints
=========

.. contents::
        :local:

.. autoklein:: flocker.control.httpapi.ConfigurationAPIUserV1
    :schema_store_fqpn: flocker.control.httpapi.SCHEMAS
    :prefix: /v1
    :examples_path: api_examples.yml
    :section: common

.. autoklein:: flocker.control.httpapi.ConfigurationAPIUserV1
    :schema_store_fqpn: flocker.control.httpapi.SCHEMAS
    :prefix: /v1
    :examples_path: api_examples.yml
    :section: dataset
