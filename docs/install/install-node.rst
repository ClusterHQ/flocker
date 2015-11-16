.. _installing-flocker-node:

====================================
Installing the Flocker Node Services
====================================

The following instructions describe how to install the ``clusterhq-flocker node`` package, and the optional ``clusterhq-flocker-docker-plugin`` package on each of the nodes in your cluster.

.. _installing-flocker-node-prereq:

Prerequisites
=============

Before you begin to install the Flocker node services, you will need the following:

* A minimum of 2 nodes:
  
  * We support installing the Flocker node services on either :ref:`CentOS 7<centos-7-install>` or :ref:`Ubuntu 14.04<ubuntu-14.04-install>`.
  * If you do not have any nodes, see our :ref:`helpful-guides` which can be used to help you set up nodes using either :ref:`Amazon Web Services<aws-install>` or :ref:`Rackspace<rackspace-install>`.
  * To avoid potential disk space problems (for example, when storing popular Docker images), we recommend a minimum of 16 GB storage on each node.

* You will need permission for SSH access from your laptop.
* Depending on your usage of Flocker, you will require access to a range of ports.
  For example, instructions on specifying which ports to make available are included in the :ref:`aws-install` documentation.
* Flocker's container management features depend on Docker.
  You will need to make sure `Docker (at least 1.8) is installed`_ and running.

.. _helpful-guides:

Helpful Guides for Setting Up Nodes
===================================

If you do not have any nodes, the following guides will help you set some up, with either AWS or Rackspace:

* :ref:`aws-install`
* :ref:`rackspace-install`

If you set up nodes with either AWS or Rackspace, you'll need to come back to the installation steps below to install the ``flocker-node`` packages specific to your operating system.

.. _centos-7-install:

Installing on CentOS 7
======================

.. note:: You should ensure your nodes are Flocker-ready, either by checking the :ref:`prerequisites<installing-flocker-node-prereq>` above, or by following our guides on using :ref:`AWS<aws-install>` or :ref:`Rackspace<rackspace-install>`.

#. **Log into the first node as root:**

   .. prompt:: bash alice@mercury:~$

      ssh root@<your-first-node>

#. **Install the** ``clusterhq-flocker-node`` **package:**

   To install ``clusterhq-flocker-node`` on CentOS 7 you must install the RPM package provided by the ClusterHQ repository.
   The commands below will install the two repositories and the ``clusterhq-flocker-node`` package.
   
   Run the following commands as root on the target node:

   .. task:: install_flocker centos-7
      :prompt: [root@centos]#

#. **Install the** ``clusterhq-flocker-docker-plugin`` **package:**

   At this point you can choose to install the Flocker plugin for Docker.
   Run the following command as root on the target node:

   .. prompt:: bash [root@centos]#
   
      yum install -y clusterhq-flocker-docker-plugin

.. XXX FLOC-3454 to create a task directive for installing the plugin

#. **Repeat the previous steps for all other nodes:**

   Log into your other nodes as root, and then complete step 2 and 3 until all the nodes in your cluster have installed the ``clusterhq-flocker-node`` and the optional ``clusterhq-flocker-docker-plugin`` package.

.. note:: Flocker's container management features depend on Docker.
          You will need to make sure `Docker (at least 1.8) is installed`_ and running.
   
.. _ubuntu-14.04-install:

Installing on Ubuntu 14.04
==========================

.. note:: You should ensure your nodes are Flocker-ready, either by checking the :ref:`prerequisites<installing-flocker-node-prereq>` above, or by following our guides on using :ref:`AWS<aws-install>` or :ref:`Rackspace<rackspace-install>`.

#. **Log into the first node as root:**

   .. prompt:: bash alice@mercury:~$

      ssh root@<your-first-node>

#. **Install the** ``clusterhq-flocker-node`` **package:**

   To install ``clusterhq-flocker-node`` on Ubuntu 14.04 you must install the package provided by the ClusterHQ repository.
   The commands below will install the two repositories and the ``clusterhq-flocker-node`` package.
   
   Run the following commands as root on the target node:
   
   .. task:: install_flocker ubuntu-14.04
      :prompt: [root@ubuntu]#

#. **Install the** ``clusterhq-flocker-docker-plugin`` **package:**

   At this point you can choose to install the Flocker plugin for Docker.
   Run the following command as root on the target node:

   .. prompt:: bash [root@ubuntu]#
   
      apt-get install -y clusterhq-flocker-docker-plugin

.. XXX FLOC-3454 to create a task directive for installing the plugin

#. **Repeat the previous steps for all other nodes:**

   Log into your other nodes as root, and then complete step 2 and 3 until all the nodes in your cluster have installed the ``clusterhq-flocker-node`` and the optional ``clusterhq-flocker-docker-plugin`` package.


.. note:: Flocker's container management features depend on Docker.
          You will need to make sure `Docker (at least 1.8) is installed`_ and running.

Next Step
=========

The installation of the Flocker clients, node services and the Flocker plugin for Docker (if chosen) is now complete.
To enable these services, and to configure your cluster security and backend, please move on to :ref:`post-installation-configuration`.

.. _Docker (at least 1.8) is installed: https://docs.docker.com/installation/
