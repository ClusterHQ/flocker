.. _post-installation-configuration:

===============================
Post-installation Configuration
===============================

The following sections describe how to complete the post-installation configuration:

.. contents::
   :local:
   :backlinks: none
   :depth: 2

It is important to remember that your firewall will need to allow access to the ports your applications are exposing.

.. warning::

   Keep in mind the consequences of exposing unsecured services to the Internet.
   Both applications with exposed ports and applications accessed via links will be accessible by anyone on the Internet.

.. _authentication:

Configuring Cluster Authentication
==================================

Communication between the different parts of your cluster is secured and authenticated via TLS.
The Flocker CLI package includes the ``flocker-ca`` tool that is used to generate TLS certificate and key files that you will need to copy over to your nodes.

#. Once you have installed the ``flocker-node`` package, you will need to generate:

   - A control service certificate and key file, to be copied over to the machine running your :ref:`control service <architecture>`.
   - A certificate and key file for each of your nodes, which you will also need to copy over to the nodes.

#. Both types of certificate will be signed by a certificate authority identifying your cluster, which is also generated using the ``flocker-ca`` tool.

#. Using the machine on which you installed the ``flocker-cli`` package, run the following command to generate your cluster's root certificate authority, replacing ``mycluster`` with any name you like to uniquely identify this cluster.

   .. prompt:: bash 

      flocker-ca initialize mycluster

   .. note:: This command creates :file:`cluster.key` and :file:`cluster.crt`.
             Please keep :file:`cluster.key` secret, as anyone who can access it will be able to control your cluster.

   You will find the files :file:`cluster.key` and :file:`cluster.crt` have been created in your working directory.

#. The file :file:`cluster.key` should be kept only by the cluster administrator; it does not need to be copied anywhere.

   .. warning:: The cluster administrator needs this file to generate new control service, node and API certificates.
                The security of your cluster depends on this file remaining private.
                Do not lose the cluster private key file, or allow a copy to be obtained by any person other than the authorized cluster administrator.

#. You are now able to generate authentication certificates for the control service and each of your nodes.
   To generate the control service certificate, run the following command from the same directory containing your authority certificate generated in the previous step:

   - Replace ``example.org`` with the hostname of your control service node; this hostname should match the hostname you will give to HTTP API clients.
   - It should be a valid DNS name that HTTPS clients can resolve since they will use it as part of TLS validation.
   - Using an IP address is not recommended as it may break some HTTPS clients.

     .. code-block:: console

        $ flocker-ca create-control-certificate example.org

#. At this point you will need to create a :file:`/etc/flocker` directory on each node:

   .. code-block:: console

      root@centos-7:~/$ mkdir /etc/flocker

#. You will need to copy both :file:`control-example.org.crt` and :file:`control-example.org.key` over to the node that is running your control service, to the directory :file:`/etc/flocker` and rename the files to :file:`control-service.crt` and :file:`control-service.key` respectively.
   You should also copy the cluster's public certificate, the :file:`cluster.crt` file.

#. On the server, the :file:`/etc/flocker` directory and private key file should be set to secure permissions via :command:`chmod`:

   .. code-block:: console

      root@centos-7:~/$ chmod 0700 /etc/flocker
      root@centos-7:~/$ chmod 0600 /etc/flocker/control-service.key

   You should copy these files via a secure communication medium such as SSH, SCP or SFTP.

   .. warning:: Only copy the file :file:`cluster.crt` to the control service and node machines, not the :file:`cluster.key` file; this must kept only by the cluster administrator.

#. You will also need to generate authentication certificates for each of your nodes.
   Do this by running the following command as many times as you have nodes; for example, if you have two nodes in your cluster, you will need to run this command twice.

   This step should be followed for all nodes on the cluster, as well as the machine running the control service.
   Run the command in the same directory containing the certificate authority files you generated in the first step.

   .. code-block:: console

      $ flocker-ca create-node-certificate

   This creates :file:`8eab4b8d-c0a2-4ce2-80aa-0709277a9a7a.crt`. Copy it over to :file:`/etc/flocker/node.crt` on your node machine, and make sure to chmod 0600 it.

   The actual certificate and key file names generated in this step will vary from the example above; when you run ``flocker-ca create-node-certificate``, a UUID for a node will be generated to uniquely identify it on the cluster and the files produced are named with that UUID.

#. As with the control service certificate, you should securely copy the generated certificate and key file over to your node, along with the :file:`cluster.crt` certificate.

   - Copy the generated files to :file:`/etc/flocker` on the target node and name them :file:`node.crt` and :file:`node.key`.
   - Perform the same :command:`chmod 600` commands on :file:`node.key` as you did for the control service in the instructions above.
   - The :file:`/etc/flocker` directory should be set to ``chmod 700``.

You should now have :file:`cluster.crt`, :file:`node.crt`, and :file:`node.key` on each of your agent nodes, and :file:`cluster.crt`, :file:`control-service.crt`, and :file:`control-service.key` on your control node.

Before you can use Flocker's API you will also need to :ref:`generate a client certificate <generate-api>`.

You can read more about how Flocker's authentication layer works in the :ref:`security and authentication guide <security>`.

Enabling the Flocker control service 
====================================

On CentOS 7
-----------

.. task:: enable_flocker_control centos-7
   :prompt: [root@control-node]#

The control service needs to be accessible remotely.
You will need to configure FirewallD to allow access to the control service HTTP API and for agent connections.
Note that on some environments, in particular AWS, the ``firewalld`` package is not installed and the ``firewall-cmd`` program will not be found.
If that is the case then just skip these commands.
Otherwise run:

.. task:: open_control_firewall centos-7
   :prompt: [root@control-node]#

For more details on configuring the firewall, see the `FirewallD documentation <https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/Security_Guide/sec-Using_Firewalls.html>`_.

On AWS, an external firewall is used instead, which will need to be configured similarly.

On Ubuntu
---------

.. task:: enable_flocker_control ubuntu-14.04
   :prompt: [root@control-node]#

The control service needs to accessible remotely.
To configure ``UFW`` to allow access to the control service HTTP API, and for agent connections:

.. task:: open_control_firewall ubuntu-14.04
   :prompt: [root@control-node]#

For more details on configuring the firewall, see Ubuntu's `UFW documentation <https://help.ubuntu.com/community/UFW>`_.

On AWS, an external firewall is used instead, which will need to be configured similarly.

.. _agent-yml:

Configuring the Flocker agent
=============================

To start the agents on a node, a configuration file must exist on the node at ``/etc/flocker/agent.yml``.
The file must always include ``version`` and ``control-service`` items similar to these:

.. code-block:: yaml

   "version": 1
   "control-service":
      "hostname": "${CONTROL_NODE}"
      "port": 4524

The value of the hostname field should be a hostname or IP that is routable from all your node agents.

When configuring node agents, consider whether the control service location you choose will have multiple possible addresses, and ensure the hostname you provide is the correct one.
You should never choose ``127.0.0.1`` or ``localhost`` as the hostname, even if the control service is on same machine as the node agent.

Please note that the interface you choose will be the one that linked traffic will be routed over.
If you're in environment where some interfaces have bandwidth costs and some are free (for example, AWS), ensure that you choose the private interface where bandwidth costs don't apply.

``${CONTROL_NODE}`` should be replaced with the address of the control node.
The optional ``port`` variable is the port on the control node to connect to.
This value must agree with the configuration for the control service telling it on what port to listen.
Omit the ``port`` from both configurations and the services will automatically agree.

The file must also include a ``dataset`` item.
This selects and configures a dataset backend.
All nodes must be configured to use the same dataset backend.

.. _openstack-dataset-backend:

OpenStack Block Device Backend Configuration
--------------------------------------------

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

Other items are typically required but vary depending on the `OpenStack authentication plugin selected <http://docs.openstack.org/developer/python-keystoneclient/authentication-plugins.html#loading-plugins-by-name>`_
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
---------------------------------------------------

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
--------------------------------------

EMC provide plugins for Flocker integration with `ScaleIO`_ and `XtremIO`_.
For more information, including installation, testing and usage instructions, visit the following links to their GitHub repositories:

* `EMC ScaleIO Flocker driver on GitHub`_
* `EMC XtremIO Flocker driver on GitHub`_

.. XXX FLOC 2442 and 2443 to expand this EMC/Backend storage section

.. _zfs-dataset-backend:

ZFS Peer-to-Peer Backend Configuration (Experimental)
-----------------------------------------------------

The ZFS backend uses node-local storage and ZFS filesystems as the storage for datasets.
The ZFS backend remains under development, it is not expected to operate reliably in many situations, and its use with any data that you cannot afford to lose is **strongly** discouraged at this time.
This backend has no infrastructure requirements: it can run no matter where the Flocker dataset agents run.
The configuration item to use ZFS should look like:

.. code-block:: yaml

   "dataset":
      "backend": "zfs"
      "pool": "flocker"

.. This section could stand to be improved.
   Some of the suggested steps are not straightforward.
   FLOC-2092

The pool name must match a ZFS storage pool that you have created on all of the Flocker agent nodes.
This requires first installing :ref:`ZFS on Linux <installing-ZFS-CentOS-7>`.
You must also set up SSH keys at ``/etc/flocker/id_rsa_flocker`` which will allow each Flocker dataset agent node to authenticate to all other Flocker dataset agent nodes as root.

.. _loopback-dataset-backend:

Loopback Block Device Backend Configuration (INTERNAL TESTING)
--------------------------------------------------------------

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

Enabling the Flocker agent service
==================================

On CentOS 7
-----------

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent centos-7
   :prompt: [root@agent-node]#

On Ubuntu
---------

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent ubuntu-14.04
   :prompt: [root@agent-node]#

What to do next
===============

Optional ZFS Backend Configuration
----------------------------------

If you intend to use a ZFS backend, this requires ZFS to be installed.

.. _installing-ZFS-CentOS-7:

Installing ZFS on CentOS 7
..........................

Installing ZFS requires the kernel development headers for the running kernel.
Since CentOS doesn't provide easy access to old package versions,
the easiest way to get appropriate headers is to upgrade the kernel and install the headers.

.. task:: upgrade_kernel centos-7
   :prompt: [root@centos-7]#

You will need to reboot the node after updating the kernel.

.. prompt:: bash [root@centos-7]#

   shutdown -r now

You must also install the ZFS package repository.

.. task:: install_zfs centos-7
   :prompt: [root@centos-7]#


Installing ZFS on Ubuntu 14.04
..............................

.. task:: install_zfs ubuntu-14.04
   :prompt: [root@ubuntu-14.04]#


Creating a ZFS Pool
...................

Flocker requires a ZFS pool.
The pool is typically named ``flocker`` but this is not required.
The following commands will create a 10 gigabyte ZFS pool backed by a file:

.. task:: create_flocker_pool_file
   :prompt: [root@node]#

.. note:: It is also possible to create the pool on a block device.

.. XXX: Document how to create a pool on a block device: https://clusterhq.atlassian.net/browse/FLOC-994

To support moving data with the ZFS backend, every node must be able to establish an SSH connection to all other nodes.
So ensure that the firewall allows access to TCP port 22 on each node from the every node's IP addresses.

Next Step
=========

The next step is to set up an :ref:`authenticated user<authenticate>`.

.. _ScaleIO: https://www.emc.com/storage/scaleio/index.htm
.. _XtremIO: https://www.emc.com/storage/xtremio/overview.htm
.. _EMC ScaleIO Flocker driver on GitHub: https://github.com/emccorp/scaleio-flocker-driver
.. _EMC XtremIO Flocker driver on GitHub: https://github.com/emccorp/xtremio-flocker-driver
