.. _installing-flocker-node:

====================================
Installing the Flocker Node Services
====================================

.. _installing-flocker-node-prereq:

Prerequisites
=============

Before you begin to install the Flocker node services, you will the following:

* You will require a minimum of 2 nodes in order to install and use Flocker:
  
  * We support installing the Flocker node services on either :ref:`CentOS 7<centos-7-install>` or :ref:`Ubuntu 14.04<ubuntu-14.04-install>`.
  * We recommend a minimum of 16GB storage on each node.

* You will need permission for SSH access from your laptop.
* Depending on your usage of Flocker, you will require access to a range of ports.
  For example, specifying which ports to make available are included in the  :ref:`aws-install` documentation.
* Flocker's container management features depend on Docker.
  You will need to make sure `Docker (at least 1.8) is installed`_ and running.

Helpful Guides
==============

If you do not have any nodes, the following guides will help you set some up, with either AWS or Rackspace:

.. toctree::
   :maxdepth: 1

   setup-aws
   setup-rackspace

If you set up nodes with either AWS or Rackspace, you'll need to come back to the installation steps below to install the ``flocker-node`` packages specific to your operating system.

.. _centos-7-install:

Installing on CentOS 7
======================

.. note:: You should ensure your nodes are Flocker-ready, either by checking the :ref:`prerequisites<installing-flocker-node-prereq>` above, or by following our guides on using :ref:`AWS<aws-install>` or :ref:`Rackspace<rackspace-install>`.

#. **Log into the first node as root.**

   .. prompt:: bash $

      ssh root@<your-first-node>

#. **Install the** ``clusterhq-flocker-node`` **package.**

   To install ``clusterhq-flocker-node`` on CentOS 7 you must install the RPM provided by the ClusterHQ repository.
   The commands below will install the two repositories and the ``clusterhq-flocker-node`` package.
   
   Paste the following commands into a root console on the target node:

   .. task:: install_flocker centos-7
      :prompt: [root@centos]#

#. **Repeat steps 1 and 2 on all other nodes.**

   If you haven't already, log into your other nodes as root, and then run step 2 until all the nodes in your cluster have installed the ``clusterhq-flocker-node`` package.

.. note:: Flocker's container management features depend on Docker.
          You will need to make sure `Docker (at least 1.8) is installed`_ and running.
   
.. _ubuntu-14.04-install:

Installing on Ubuntu 14.04
==========================

.. note:: You should ensure your nodes are Flocker-ready, either by checking the :ref:`prerequisites<installing-flocker-node-prereq>` above, or by following our guides on using :ref:`AWS<aws-install>` or :ref:`Rackspace<rackspace-install>`.

#. **Log into the first node as root.**

   .. prompt:: bash $

      ssh root@<your-first-node>

#. **Install the** ``clusterhq-flocker-node`` **package.**

   To install ``clusterhq-flocker-node`` on Ubuntu 14.04 you must install the package provided by the ClusterHQ repository.
   The commands below will install the two repositories and the ``clusterhq-flocker-node`` package.
   
   Paste the following commands into a root console on the target node:
   
   .. task:: install_flocker ubuntu-14.04
      :prompt: [root@ubuntu]#

#. **Repeat steps 1 and 2 on all other nodes.**

   If you haven't already, log into your other nodes as root, and then run step 2 until all the nodes in your cluster have installed the ``clusterhq-flocker-node`` package.

.. note:: Flocker's container management features depend on Docker.
          You will need to make sure `Docker (at least 1.8) is installed`_ and running.


Finally, you will need to run the ``flocker-ca`` tool that is installed as part of the CLI package.
This tool generates TLS certificates that are used to identify and authenticate the components of your cluster when they communicate, which you will need to copy over to your nodes.
Please continue onto the next section, with the cluster authentication instructions.

Next Step
=========

You are now ready to :ref:`install the Flocker plugin for Docker<install-docker-plugin>`, which allows Flocker to manage your data volumes while using other tools such as Docker, Docker Swarm, or Mesos to manage your containers.

Alternatively, you can go ahead to the next section, where you will need to  :ref:`configure your cluster<post-installation-configuration>`, starting with setting up authentication so the different parts of Flocker can communicate.

.. _Docker (at least 1.8) is installed: https://docs.docker.com/installation/
