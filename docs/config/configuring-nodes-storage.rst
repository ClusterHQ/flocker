.. _agent-yml:

==========================================
Configuring the Nodes and Storage Backends
==========================================

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

Please note that the interface you choose will be the one that linked traffic will be routed over.
If you're in environment where some interfaces have bandwidth costs and some are free (for example, AWS), ensure that you choose the private interface where bandwidth costs don't apply.

``${CONTROL_NODE}`` should be replaced with the address of the control node.
The optional ``port`` variable is the port on the control node to connect to.
This value must agree with the configuration for the control service telling it on what port to listen.
Omit the ``port`` from both configurations and the services will automatically agree.

The ``dataset`` item selects and configures a dataset backend.
All nodes must be configured to use the same dataset backend.

.. note::
	You can only choose a single backend at a time, and changing backends is not currently supported.

Storage Profiles
================

.. include:: ../concepts/storage-profiles.rst
   :start-after: .. begin-body
   :end-before: .. end-body

.. _supported-backends:

Supported Backends
==================

The following pages describe how to configure the backends currently supported by Flocker.

ClusterHQ supported drivers:

.. toctree::
   :maxdepth: 1

   aws-configuration
   openstack-configuration
   loopback-configuration

Community supported drivers:

.. toctree::
   :maxdepth: 1

   convergeio-configuration
   dell-configuration
   emc-configuration
   hedvig-configuration
   huawei-configuration
   netapp-configuration
   nexenta-configuration
   saratogaspeed-configuration
   vmware-configuration
   
Flocker supports pluggable storage backends. 
Any storage system that is able to present itself as a network-based block device can serve as the underlying storage for a Docker data volume managed by Flocker.
If the storage backend you are looking for is not currently supported by Flocker, you can consider :ref:`contributing it <build-flocker-driver>`.
