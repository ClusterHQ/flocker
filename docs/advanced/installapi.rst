.. _api:

=============================
Flocker REST API Installation
=============================

We are currently in the process of developing an external HTTP-based REST API for Flocker.
While this API is not yet directly accessible in a standard Flocker setup, the documentation below will give a sense of what will eventually be available.

Fedora/CentOS
-------------

To enable the Flocker control service.

.. task:: enable_flocker_control
   :prompt: [root@control-node]#

The control service needs to accessible remotely.
To configure firewalld to allow access to the control service REST API, and for agent connections,

.. task:: open_control_firewall

(On AWS, an external firewall is used instead, which will need to be configured similarity).
For more details on configuring the firewall, see Fedora's `FirewallD documentation <https://fedoraproject.org/wiki/FirewallD>`_.

To start the agent on a node, (where ``${CONTROL_NODE}`` is the address of the control node, and ``${NODE_NAME}`` is the name of the node being configured).:

.. task:: enable_flocker_agent ${NODE_NAME} ${CONTROL_NODE}
   :prompt: [root@agent-node]#