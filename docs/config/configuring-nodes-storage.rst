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

The following sections describe how to configure the backends currently supported by Flocker:

.. contents::
   :local:
   :backlinks: none
   :depth: 1

.. XXX FLOC 2442 improves this section, by creating a page solely for a list of supported backends, which is scaleable as the list grows.

.. _openstack-dataset-backend:

OpenStack Block Device Backend Configuration
============================================

The OpenStack backend uses Cinder volumes as the storage for datasets.
This backend can be used with Flocker dataset agent nodes run by OpenStack Nova.
The configuration item to use OpenStack should look like:

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "<region slug; for example, LON>"
       auth_plugin: "<authentication plugin>"
       ...

Make sure that the ``region`` specified matches the region where the Flocker nodes run.
OpenStack must be able to attach volumes created in that region to your Flocker agent nodes.

.. note::
	For the Flocker OpenStack integration to be able to identify the virtual machines where you run the Flocker agents, and to attach volumes to them, those virtual machines **must be provisioned through OpenStack** (via Nova).

.. XXX FLOC-2091 - Fix up this section.

If the OpenStack cloud uses certificates that are issued by a private Certificate Authority (CA), add the field ``verify_ca_path`` to the dataset stanza, with the path to the CA certificate.

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "DFW"
       verify_ca_path: "/etc/flocker/openstack-ca.crt"
       auth_plugin: "password"
       ...

For testing purposes, it is possible to turn off certificate verification, by setting the ``verify_peer`` field to ``false``.

.. warning::

   Only use this insecure setting for troubleshooting, as it is does not check that the remote server's credential is valid.

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "DFW"
       verify_peer: false
       auth_plugin: "password"
       ...

Other items are typically required but vary depending on the `OpenStack authentication plugin selected`_
(Flocker relies on these plugins; it does not provide them itself).

Flocker does provide explicit support for a ``rackspace`` authentication plugin.
This plugin requires ``username``, ``api_key``, and ``auth_url``.

For example:

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "<region slug; for example, LON>"
       auth_plugin: "rackspace"
       username: "<your rackspace username>"
       api_key: "<your rackspace API key>"
       auth_url: "https://identity.api.rackspacecloud.com/v2.0"

To find the requirements for other plugins, see the appropriate documentation in the OpenStack project or provided with the plugin.

.. _aws-dataset-backend:

Amazon AWS / EBS Block Device Backend Configuration
===================================================

The AWS backend uses EBS volumes as the storage for datasets.
This backend can be used when Flocker dataset agents are run on EC2 instances.
The configuration item to use AWS should look like:

.. code-block:: yaml

   dataset:
       backend: "aws"
       region: "<region slug; for example, us-west-1>"
       zone: "<availability zone slug; for example, us-west-1a>"
       access_key_id: "<AWS API key identifier>"
       secret_access_key: "<Matching AWS API key>"

Make sure that the ``region`` and ``zone`` match each other and that both match the region and zone where the Flocker agent nodes run.
AWS must be able to attach volumes created in that availability zone to your Flocker nodes.

.. _emc-dataset-backend:

EMC Block Device Backend Configuration
======================================

EMC provide plugins for Flocker integration with `ScaleIO`_ and `XtremIO`_.
For more information, including installation, testing and usage instructions, visit the following links to their GitHub repositories:

* `EMC ScaleIO Flocker driver on GitHub`_
* `EMC XtremIO Flocker driver on GitHub`_

.. XXX FLOC 2442 and 2443 to expand this EMC/Backend storage section

.. _zfs-dataset-backend:

ZFS Peer-to-Peer Backend Configuration (EXPERIMENTAL)
=====================================================

The ZFS backend uses node-local storage and ZFS filesystems as the storage for datasets.
The ZFS backend remains under development, it is not expected to operate reliably in many situations, and its use with any data that you cannot afford to lose is **strongly** discouraged at this time.

To begin with, you will need to install ZFS on your platform, followed by creating a ZFS pool and configuring the ZFS backend:

.. _installing-ZFS-CentOS-7:

Installing ZFS on CentOS 7
--------------------------

Installing ZFS requires the kernel development headers for the running kernel.
Since CentOS doesn't provide easy access to old package versions, the easiest way to get appropriate headers is to upgrade the kernel and install the headers.

.. task:: upgrade_kernel centos-7
   :prompt: [root@centos-7]#

You will need to reboot the node after updating the kernel.

.. prompt:: bash [root@centos-7]#

   shutdown -r now

You must also install the ZFS package repository.

.. task:: install_zfs centos-7
   :prompt: [root@centos-7]#


Installing ZFS on Ubuntu 14.04
------------------------------

.. task:: install_zfs ubuntu-14.04
   :prompt: [root@ubuntu-14.04]#


Creating a ZFS Pool
-------------------

Flocker requires a ZFS pool.
The pool is typically named ``flocker`` but this is not required.
The following commands will create a 10 gigabyte ZFS pool backed by a file:

.. task:: create_flocker_pool_file
   :prompt: [root@node]#

.. note:: It is also possible to create the pool on a block device.

.. XXX: Document how to create a pool on a block device: https://clusterhq.atlassian.net/browse/FLOC-994

To support moving data with the ZFS backend, every node must be able to establish an SSH connection to all other nodes.
So ensure that the firewall allows access to TCP port 22 on each node from the every node's IP addresses.

You must also set up SSH keys at :file:`/etc/flocker/id_rsa_flocker` which will allow each Flocker dataset agent node to authenticate to all other Flocker dataset agent nodes as root.

ZFS Backend Configuration
-------------------------

The configuration item to use ZFS should look like:

.. code-block:: yaml

   "dataset":
      "backend": "zfs"
      "pool": "flocker"

.. This section could stand to be improved.
   Some of the suggested steps are not straightforward.
   FLOC-2092

The pool name must match a ZFS storage pool that you have created on all of the Flocker agent nodes. For more information, see the `ZFS on Linux`_ documentation.

.. _loopback-dataset-backend:

Loopback Block Device Backend Configuration (INTERNAL TESTING)
==============================================================

The Loopback backend uses node-local storage as storage for datasets.
It has no data movement functionality.
It serves primarily as a development and testing tool for the other block device backend implementations.
You may find it useful if you plan to work on Flocker itself.
This backend has no infrastructure requirements: it can run no matter where the Flocker dataset agents run.
The configuration item to use Loopback should look like:

.. code-block:: yaml

   "dataset":
      "backend": "loopback"
      "root_path": "/var/lib/flocker/loopback"

The ``root_path`` is a local path on each Flocker dataset agent node where dataset storage will reside.

.. _OpenStack authentication plugin selected: http://docs.openstack.org/developer/python-keystoneclient/authentication-plugins.html#loading-plugins-by-name
.. _ScaleIO: https://www.emc.com/storage/scaleio/index.htm
.. _XtremIO: https://www.emc.com/storage/xtremio/overview.htm
.. _EMC ScaleIO Flocker driver on GitHub: https://github.com/emccorp/scaleio-flocker-driver
.. _EMC XtremIO Flocker driver on GitHub: https://github.com/emccorp/xtremio-flocker-driver
.. _ZFS on Linux: http://zfsonlinux.org/
