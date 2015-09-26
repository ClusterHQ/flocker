.. _zfs-dataset-backend:

=====================================================
ZFS Peer-to-Peer Backend Configuration (EXPERIMENTAL)
=====================================================

The ZFS backend uses node-local storage and ZFS filesystems as the storage for datasets.
The ZFS backend remains under development, it is not expected to operate reliably in many situations, and its use with any data that you cannot afford to lose is **strongly** discouraged at this time.

To begin with, you will need to install ZFS on your platform, followed by creating a ZFS pool and configuring the ZFS backend:

.. _installing-ZFS-CentOS-7:

Installing ZFS on CentOS 7
==========================

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
==============================

.. task:: install_zfs ubuntu-14.04
   :prompt: [root@ubuntu-14.04]#


.. _zfs-creating-pool:

Creating a ZFS Pool
===================

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
=========================

The configuration item to use ZFS should look like:

.. code-block:: yaml

   "dataset":
      "backend": "zfs"
      "pool": "flocker"

.. This section could stand to be improved.
   Some of the suggested steps are not straightforward.
   FLOC-2092

The pool name must match a ZFS storage pool that you have created on all of the Flocker agent nodes. For more information, see the `ZFS on Linux`_ documentation.

.. _ZFS on Linux: http://zfsonlinux.org/
