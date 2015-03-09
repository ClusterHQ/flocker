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

To enable flocker control, and allow remote access to the control agent REST API, and for agent connections,

.. task:: enable_flocker_control
   :prompt: [root@control-node]#

For more details on configuring the firewall, see Fedora's `FirewallD documentation <https://fedoraproject.org/wiki/FirewallD>`_.

To start the ZFS agent on a node, (where ``${CONTROL_NODE}`` is the address of the control node, and ``${NODE_NAME}`` is the name of the node being configured.:

.. task:: enable_flocker_agent ${NODE_NAME} ${CONTROL_NODE}
   :prompt: [root@agent-node]#

API Details
===========

In general the API allows for modifying the desired configuration of the cluster.
When you use the API to change the configuration, e.g. creating a new dataset:

#. A successful response indicates a change in configuration, not a change to cluster state.
#. Convergence agents will then take the necessary actions and eventually the cluster's state will match the requested configuration.
#. The actual cluster state will then reflect the requested change.
   E.g. cluster datasets state can be accessed via :http:get:`/v1/state/datasets`.

For more information read the :ref:`cluster architecture<architecture>` documentation.

.. autoklein:: flocker.control.httpapi.DatasetAPIUserV1
    :schema_store_fqpn: flocker.control.httpapi.SCHEMAS
    :prefix: /v1
    :examples_path: api_examples.yml
