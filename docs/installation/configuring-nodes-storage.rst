.. Single Source Instructions

==========================================
Configuring the Nodes and Storage Backends
==========================================

.. begin-body-nodeconfig-agent-yml

To start the agents on a node, a configuration file must exist on the node at :file:`/etc/flocker/agent.yml`.
The file must always include ``version`` and ``control-service`` items, and will need to include ``dataset`` objects similar to these:

.. code-block:: yaml

   "version": 1
   "control-service":
      "hostname": "${CONTROL_NODE}"
      "port": 4524

   # The dataset key below selects and configures a dataset backend (see below: aws/openstack/etc).
   # All nodes will be configured to use only one backend

   dataset:
      backend: "aws"
      region: "<your region; for example, us-west-1>"
      zone: "<your availability zone; for example, us-west-1a>"
      access_key_id: "<AWS API key identifier>"
      secret_access_key: "<Matching AWS API key>"

The value of the ``hostname`` field should be a hostname or IP that is routable from all your node agents.

When configuring node agents, consider whether the location you choose for the Flocker control service will have multiple possible addresses, and ensure the hostname you provide is the correct one.

.. warning::
	You should never choose ``127.0.0.1`` or ``localhost`` as the hostname, even if the control service is on same machine as the node agent, as this will keep the control service from correctly identifying the agent's IP address.

	It is also important to be aware that the flocker nodes will refuse to communicate with the flocker agent if there is a misconfiguration in the hostname.
	Please ensure that your hostname is configured correctly before proceeding, because any errors can result in failures.

Please note that the interface you choose will be the one that Flocker control traffic will be routed over.
If you're in environment where some interfaces have bandwidth costs and some are free (for example, AWS), ensure that you choose the private interface where bandwidth costs don't apply.

``${CONTROL_NODE}`` should be replaced with the address of the control node.
The optional ``port`` variable is the port on the control node to connect to.
This value must agree with the configuration for the control service telling it on what port to listen.
Omit the ``port`` from both configurations and the services will automatically agree.

The ``dataset`` item selects and configures a dataset backend.
All nodes must be configured to use the same dataset backend.

Choose and Configure Your Backend
=================================

For a full list of available storage backends, see :ref:`supported-backends`.

.. warning::
	You can only choose a single backend at a time, and changing backends is not currently supported.
	
	Each :ref:`backend <supported-backends>` provides configuration details for you to setup the driver.
	When your driver is configured, you will need to return to complete the Flocker installation process.

.. end-body-nodeconfig-agent-yml
