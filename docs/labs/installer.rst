.. _labs-installer:

=========
Installer
=========

This document guides you through setting up a Flocker cluster and gives the simplest example of deploying and moving around some stateful containers.

Key points
==========

* Flocker is a clustered container data volume manager.
  This means it runs on a cluster (a group) of machines, and connects containers to data volumes so that containers which store data, such as databases, keep their data as they move around the cluster.
* Flocker is installed on servers, which you must provision, for example on cloud infrastructure.
* It works with other container tools, such as Swarm, Compose and Mesos/Marathon.

Architecture
============

This diagram shows you what you are about to set up.

.. image:: install-architecture.png

.. Source file is at "Engineering/Labs/flocker architecture" https://drive.google.com/open?id=0B3gop2KayxkVbmNBR2Jrbk0zYmM

* Installer runs in a Docker container on your local machine.
* You provision the servers yourself, then write a ``cluster.yml`` in your cluster directory containing the addresses of the servers.
* You run the installer on the ``cluster.yml``.
* Installer creates certificates for you, saves them in your cluster directory, and installs Flocker and certificates on servers, starts Flocker.
* You can now interact with your Flocker cluster using the Flocker CLI (included in same container as installer).

Supported Configurations
========================

The Installer can be used in the following configurations.

* **Supported configurations**

  * Ubuntu or CentOS on AWS with EBS backend
  * Ubuntu or CentOS on Rackspace with OpenStack backend
  * Ubuntu or CentOS on private OpenStack cloud with OpenStack backend

* **Experimental configurations**

  * CoreOS on AWS with EBS backend
  * Ubuntu or CentOS on any infrastructure with experimental ZFS backend

Other configurations may work, but have not been tested.

.. _labs-installing-unofficial-flocker-tools:

Installing the Installer
========================

First we install the installer on your workstation.
We do this by running a tiny script which puts some wrapper scripts in ``/usr/local/bin``.

This will work on Linux or OS X machines with Docker installed.
If you don't have Docker installed, install it now (`Mac <https://docs.docker.com/mac/started/>`_, `Linux <https://docs.docker.com/mac/started/>`_).

Then install the installer:

.. prompt:: bash $

    curl -sSL https://get.flocker.io/ | sudo sh

.. _labs-installer-certs-directory:

Make a local directory for your cluster files
=============================================

The tools will create some configuration files and certificate files for your cluster.
It is convenient to keep these in a directory, so let's make a directory on your workstation like this:

.. prompt:: bash $

    mkdir -p ~/clusters/test
    cd ~/clusters/test

Later on we'll put some files in this directory.

Get some nodes
==============

So now let's use the tools we've just installed to deploy and configure a Flocker cluster quickly!

Provision some machines on AWS or an OpenStack deployment (e.g. Rackspace), or bare metal if you want to try out the experimental ZFS backend.
Use Ubuntu 14.04, CentOS 7, or CoreOS.

.. warning::
    CoreOS support is experimental, and should not be used for production workloads.
    ZFS support is similarly experimental.

We recommend Ubuntu 14.04 if you want to try the Flocker Docker plugin.

Make sure you create the servers a reasonable amount of disk space, since Docker images will be stored on the VM root disk itself.

* Use Amazon EC2 if you want to use our EBS backend.
  **VMs must be deployed in the same AZ.**
* Use an OpenStack deployment (e.g. Rackspace, private cloud) if you want to try our OpenStack backend.
  **VMs must be deployed in the same region.**

You may want to pick a node to be the control node and give it a DNS name (if you do this, set up an A record for it with your DNS provider).
Using a DNS name is optional, you can also just use its IP address.

cluster.yml
===========

Run the following command in your ``~/clusters/test`` directory you made earlier:

.. prompt:: bash $

    uft-flocker-sample-files

This will create some sample configuration files that correspond to the backend Flocker will use - base your ``cluster.yml`` on one of these files:

* AWS EBS: ``cluster.yml.ebs.sample``
* OpenStack (including Rackspace): ``cluster.yml.openstack.sample``
* ZFS (local storage): ``cluster.yml.zfs.sample``

.. warning::
    Note that ZFS support is experimental, and should not be used for production workloads.

Choose the one that's appropriate for you, and then customize it with your choice of text editor.
For example:

.. prompt:: bash $

    mv cluster.yml.ebs.sample cluster.yml
    vim cluster.yml # customize for your cluster

.. note::

    You need a private key which can log into the machines - you can configure this in the ``private_key_path`` of ``cluster.yml``.

Install Flocker
===============

From the directory where your ``cluster.yml`` file is now, run the following command:

.. prompt:: bash $

    flocker-install cluster.yml

This will install the OS packages on your nodes required to run Flocker.
Flocker is not ready to run yet, we still need to do some certificate management.


Configure Certificates
======================

From the directory where your ``cluster.yml`` file is now, run the following command:

.. prompt:: bash $

    flocker-config cluster.yml

This will configure certificates, push them to your nodes, and set up firewall rules for the control service.

.. warning::
    On AWS, you also need to add a firewall rule allowing traffic for TCP port 4523 and 4524.

Install Flocker Docker plugin
=============================

If you want to install the :ref:`Flocker Docker plugin <labs-docker-plugin>` then follow these steps.
Currently this has only been tested on Ubuntu 14.04 and CoreOS.

Please keep in mind :ref:`this note on architecture <labs-architecture-note>`.

From the directory where your ``cluster.yml`` file is now, run the following command:

.. prompt:: bash $

    flocker-plugin-install cluster.yml

This will configure API certificates for the Flocker Docker plugin and push them to your nodes - it will name them ``/etc/flocker/plugin.{crt,key}`` on the nodes.

It will also download and install a Docker binary that supports the ``--volume-driver`` flag and restart the Docker service.

Once you've installed the Flocker Docker plugin, check out the experimental :ref:`volumes CLI <labs-volumes-cli>` and :ref:`GUI <labs-volumes-gui>`, and the :ref:`Swarm <labs-swarm>` and :ref:`Compose <labs-compose>` integrations.
