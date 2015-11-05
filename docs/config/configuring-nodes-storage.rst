.. _agent-yml:

==========================================
Configuring the Nodes and Storage Backends
==========================================

To start the agents on a node, a configuration file must exist on the node at ``/etc/flocker/agent.yml``.
The file must always include ``version`` and ``control-service`` items similar to these:

.. code-block:: yaml

   "version": 1
   "control-service":
      "hostname": "${CONTROL_NODE}"
      "port": 4524

The value of the hostname field should be a hostname or IP that is routable from all your node agents.

When configuring node agents, consider whether the control service location you choose will have multiple possible addresses, and ensure the hostname you provide is the correct one.
You should never choose ``127.0.0.1`` or ``localhost`` as the hostname, even if the control service is on same machine as the node agent, as this will keep the control service from correctly identifying the agent's IP address.

.. warning::
	It is important to note that the flocker nodes will refuse to communicate with the flocker agent if there is a misconfiguration in the hostname.
	Please ensure that your hostname is configured correctly before proceeding, because any errors can result in failures.

Please note that the interface you choose will be the one that linked traffic will be routed over.
If you're in environment where some interfaces have bandwidth costs and some are free (for example, AWS), ensure that you choose the private interface where bandwidth costs don't apply.

``${CONTROL_NODE}`` should be replaced with the address of the control node.
The optional ``port`` variable is the port on the control node to connect to.
This value must agree with the configuration for the control service telling it on what port to listen.
Omit the ``port`` from both configurations and the services will automatically agree.

The file must also include a ``dataset`` item.
This selects and configures a dataset backend.
All nodes must be configured to use the same dataset backend.

.. note::
	You can only choose a single backend at a time, and changing backends is not currently supported.

Storage Profiles
================

Flocker Storage Profiles are a way to help you choose different levels of service from your storage provider.
For example, in a development environment you might only want a low cost storage option.
However, if you need storage for a production environment, you can choose a high performace and more expensive option.

Flocker Storage Profiles require support from your storage driver, and you are able to choose from the following profiles:

* Gold: This profile is typically for high performance storage.
* Silver: This profile is typically the intermediate, or default storage.
* Bronze: This profile is typically for low cost storage.

Please be aware that the actual specification of these profiles may differ between each storage provider.
The definition for each profile should be documented in the storage providers documentation.

.. note::
	Flocker Storage Profiles is a new and exciting implementation, but it currently only has minimal features.
	If you use a Storage Profile, it would be great to :ref:`hear from you <talk-to-us>` about how you use it and what features you would like to see in future releases.

List of Supported Backends
==========================

The following pages describe how to configure the backends currently supported by Flocker:

.. toctree::
   :maxdepth: 1
   
   openstack-configuration
   aws-configuration
   emc-configuration
   vmware-configuration
   netapp-configuration
   hedvig-configuration
   convergeio-configuration
   saratogaspeed-configuration
   zfs-configuration
   loopback-configuration
   
Flocker supports pluggable storage backends. 
Any storage system that is able to present itself as a network-based block device can serve as the underlying storage for a Docker data volume managed by Flocker.
If the storage backend you are looking for is not currently supported by Flocker, you can consider :ref:`contributing it <build-flocker-driver>`.
