.. _api:

================
Flocker REST API
================

We are currently in the process of developing an external HTTP-based REST API for Flocker.
While this API is not yet directly accessible in a standard Flocker setup, the documentation below will give a sense of what will eventually be available.


Installation
============

Fedora/CentOS
-------------

To enable the Flocker control service.

.. task:: enable_flocker_control
   :prompt: [root@control-node]#

The control service needs to accessible remotely.
To configure firewalld to allow access to the control service REST API, and for agent connections,

.. task:: open_control_firewall

(On AWS, an external firewall is used instead, which will need to be configured similarity).
For more details on configuring the firewall, see Fedora's `firewalld documentation <https://fedoraproject.org/wiki/FirewallD>`_.

To start the agents on a node, a configuration file must exist on the node at ``/etc/flocker/dataset-agent.yml``.
This file has the format:


.. code-block:: yaml

   node-name:
   control-service-endpoint: tcp:control-service-hostname:4524
   dataset:
      backend: zfs
      zfs-pool: flocker

.. Remove this before doing a release (JIRA-XXX)

or if loopback, dataset key is like:

.. code-block:: yaml

   dataset:
      backend: loopback
      loopback-pool: /var/lib/flocker/loopback

To start the agents on a node, (where ``${CONTROL_NODE}`` is the address of the control node,
``${NODE_NAME}`` is the name of the node being configured),
and ``${BACKEND}`` is either ``zfs`` or ``loopback``:


.. task:: enable_flocker_agent ${NODE_NAME} ${CONTROL_NODE} ${BACKEND}
   :prompt: [root@agent-node]#

API Details
===========

In general the API allows for modifying the desired configuration of the cluster.
When you use the API to change the configuration, e.g. creating a new dataset:

#. A successful response indicates a change in configuration, not a change to cluster state.
#. Convergence agents will then take the necessary actions and eventually the cluster's state will match the requested configuration.
#. The actual cluster state will then reflect the requested change.
   E.g. cluster datasets state can be accessed via :http:get:`/v1/state/datasets`.

.. XXX: Document the response when input validation fails:
.. https://clusterhq.atlassian.net/browse/FLOC-1613

For more information read the :ref:`cluster architecture<architecture>` documentation.

.. autoklein:: flocker.control.httpapi.ConfigurationAPIUserV1
    :schema_store_fqpn: flocker.control.httpapi.SCHEMAS
    :prefix: /v1
    :examples_path: api_examples.yml
