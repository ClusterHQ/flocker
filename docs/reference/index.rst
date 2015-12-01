.. _api:

================
Flocker REST API
================

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

.. toctree::
   :maxdepth: 2

   api
   deprecated_api

.. XXX: Improvements to the API (create collapse directive) requires Engineering effort:
.. https://clusterhq.atlassian.net/browse/FLOC-2094


.. XXX: Document the Python ``FlockerClient`` API.
.. https://clusterhq.atlassian.net/browse/FLOC-3306
