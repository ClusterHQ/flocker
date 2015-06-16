==============================
Tutorial: Moving a Data Volume
==============================

.. note:: This tutorial takes roughly 30 minutes, but because there are a few things to download, times might vary depending on the speed of your connection.

.. contents:: 
   :local:
   :backlinks: none
   :depth: 2

You will use Flocker to migrate a Docker container with its data volume from one node to another.
The container you move will be part of a two-container application, the other container will not move and the two will remain connected even when they are on different nodes.

To begin the tutorial you will first install the Flocker client on your local machine, then install Flocker onto two nodes.
You will then be ready to use Flocker to migrate a Docker container with a volume attached from one node to the other.

You will be controlling your Flocker cluster via the CLI that you will have installed locally.
The following diagram illustrates the initial server-side Flocker setup that you will control via the CLI:

.. image:: images/flocker-tutorial-initial-setup.svg
   :alt: In the initial server-side Flocker setup there are two servers, one of which has two Docker containers running; one container is a running a web application, the other has a Redis database with a volume.
   :align: center

The following diagram illustrates how the server-side Flocker setup will be configured at the end of the tutorial:

.. image:: images/flocker-tutorial-final-setup.svg
   :alt: Following the completion of this tutorial the server-side Flocker setup will be configured with the web application still running within a container on the first server, while the Redis server with a volume is running on the second server.
   :align: center

Flocker manages the data migration and the link between the two containers.

If you have any feedback or problems, you can :ref:`talk-to-us`.

Before You Begin
================

Requirements
------------

To replicate the steps demonstrated in this tutorial, you will need:

* Ubuntu 14.04, Ubuntu 15.04 or OS X with `Homebrew`_.
* Two Virtual Machines (VMs) on your local machine.
  For this tutorial, you are supplied with Vagrant images to create the tutorial environment on VMs using VirtualBox, so you must have `Vagrant`_ and `VirtualBox`_ installed.
* At least 4GB RAM available.

Installing the Client
=====================

The Flocker client runs locally on your machine, and will control the two instances of Flocker located on the nodes.
To install the Flocker client, run the following:

OS X
----

.. task:: test_homebrew flocker-|latest-installable|
   :prompt: you@laptop:~$

Ubuntu 14.04
------------

.. task:: install_cli ubuntu-14.04
   :prompt: you@laptop:~$

Ubuntu 15.04
------------

.. task:: install_cli ubuntu-15.04
   :prompt: you@laptop:~$

Installing Flocker on Local VMs
===============================

In this step, you will install two instances of Flocker, each on a separate node.
Flocker manages the links, ports, and volumes associated with Docker containers and can move them around after deployment.

#. Download the Vagrant configuration file, and the cluster and user credentials:

   .. version-code-block:: console

      you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/Vagrantfile
      you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/cluster.crt
      you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/user.crt
      you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/user.key

#. Use ``vagrant up`` to start and provision the VMs:

   .. prompt:: bash you@laptop:~$

      vagrant up

Deploying an Application on the First Node
==========================================

You will now have the client installed on your local machine, and two instances of Flocker, each on a different node.
The next step is to create two Docker containers on one of the nodes.
One container has a Python web application and the other has a Redis server, which stores its data on a volume.

Now you can try our simple tutorial: a Python web application and a Redis server.
Before you begin, you'll need to download our sample ``YAML`` files:

.. container:: hidden

   .. Create the files to be downloaded with ``cURL``, but don't show download links for them.

   :download:`docker-compose.yml`
   :download:`deployment-node1.yml`
   :download:`deployment-node2.yml`
		 
.. version-code-block:: console

   you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/docker-compose.yml
   you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/deployment-node1.yml
   you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/deployment-node2.yml

.. XXX The version-code-block presents a different style to prompts, so this document would benefit from FLOC 2141 (version-prompt)

The :file:`docker-compose.yml` file describes your distributed application:

.. literalinclude:: docker-compose.yml
   :language: yaml

The :file:`deployment-node1.yml` file describes which containers to deploy, and where:

.. literalinclude:: deployment-node1.yml
   :language: yaml

#. Use the Flocker CLI to deploy both your web application and server onto one of the virtual machines that you have just created:

   .. prompt:: bash you@laptop:~$

      flocker-deploy 172.16.255.250 deployment-node1.yml docker-compose.yml

#. View both the containers running on the first node:

   .. prompt:: bash you@laptop:~$
   
      vagrant ssh node1 -c 'docker ps'

#. Visit http://172.16.255.250/, where you will see the visit count displayed.

#. Visit http://172.16.255.251/, where you will see that the count persists because Flocker routes the traffic from either node named in the deployment file to the one that has the application.

Migrating a Container to the Second Node
========================================

The diagram below illustrates your current server-side Flocker setup:

.. image:: images/flocker-tutorial-initial-setup.svg
   :alt: In the server-side Flocker setup there are two servers, one of which has two Docker containers running; one container is a running a web application, the other has a Redis database with a volume.
   :align: center

Now we use the :file:`deployment-node2.yml` file to move the Redis container along with its data volume:

.. literalinclude:: deployment-node2.yml
   :language: yaml

#. Use the Flocker CLI to migrate one of the containers to the second node:

   .. prompt:: bash you@laptop:~$

      flocker-deploy 172.16.255.250 deployment-node2.yml docker-compose.yml

#. View the Redis container and its volume now running on the second node:

   .. prompt:: bash you@laptop:~$
   
      vagrant ssh node2 -c 'docker ps'

#. Revisit http://172.16.255.250/, where you will see the visit count is still persisted.

#. Revisit http://172.16.255.251/, and you will see that the count still persists, even though the container with the volume has moved between nodes, which would not have been possible without using Flocker.

Result
======

You have now set up your first Flocker cluster and moved a Docker container with its volume, while persisting its link to a web app on another server.

The following diagram illustrates how your server-side Flocker setup looks now:

.. image:: images/flocker-tutorial-final-setup.svg
   :alt: The web application is still running within a container on the first server, while the Redis server with a volume is now running on the second server.
   :align: center

The next Flocker tutorial is :ref:`Deploying and Migrating MongoDB <tutmongo>`, which will teach you how to use Flocker's container, network, and volume orchestration functionality, using MongoDB as an example.
You will now already have some of the pre-requisites installed (for example, ``Vagrant`` and ``VirtualBox``), but it's worth reading the :ref:`Requirements section<tutvagrant>` to check what else you'll need.

.. _`Homebrew`: http://brew.sh/
.. _`Vagrant`: https://docs.vagrantup.com/
.. _`VirtualBox`: https://www.virtualbox.org/
