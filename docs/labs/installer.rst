.. _labs-installer:

=========
Installer
=========

This document guides you through setting up a Flocker cluster and gives a simple example of deploying and moving around a service which includes a stateful container.

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
* You give the installer your cloud infrastructure credentials.
* Installer provisions servers for you, and it writes a ``cluster.yml`` in your cluster directory containing the addresses of the servers.
* You run the installer on the ``cluster.yml``.
* Installer creates certificates for you, saves them in your cluster directory, installs Flocker and certificates on servers, and starts Flocker.
* You can now interact with your Flocker cluster using the ``docker`` CLI on the nodes, or locally by using the ``uft-flocker-deploy`` tool or the ``uft-flocker-volumes`` tool.

.. _labs-supported-configurations:

Supported Configurations
========================

This Quick Start Installer can be used in the following configurations.

* **Supported configurations**

  * Ubuntu 14.04 on AWS with EBS backend

..  * Ubuntu 14.04 on Rackspace with OpenStack backend
..  * Ubuntu 14.04 on private OpenStack cloud with OpenStack backend
..
.. * **Experimental configurations**
..
..  * CoreOS on AWS with EBS backend
..  * Ubuntu 14.04 on any infrastructure with ZFS backend

Other configurations (CentOS, OpenStack, ZFS, etc) are possible via the :ref:`official long-form install docs <installing-flocker>`.

You may also be interested in the long-form documentation if you like to see exactly how things are done, or if you're automating setting up Flocker within your own configuration management system.

.. note::

    If you get an error response from any of the commands in this guide, please `report a bug <https://github.com/clusterhq/unofficial-flocker-tools/issues>`_, pasting the ``install-log.txt`` file you will find in the current directory.

.. _labs-installing-unofficial-flocker-tools:

Installing the Installer
========================

First we install the installer on your workstation.
This will work on Linux or OS X machines with Docker installed.

* If you don't have Docker installed, install it now (`Mac <https://docs.docker.com/mac/started/>`_, `Linux <https://docs.docker.com/linux/started/>`_).
  Check that Docker is working, for example by running:

  .. prompt:: bash $

      docker ps

  You should get a (possibly empty) list of running containers on your machine.

* Then install the installer, which will pull the Docker image:

  .. prompt:: bash $

      curl -sSL https://get.flocker.io/ | sh

  This assumes that your user can use ``sudo``, and may prompt you for your password.
  This installer is a tiny script which puts some wrapper scripts (around ``docker run`` commands) into your ``/usr/local/bin``.

* Now test one of the installed tools:

  .. prompt:: bash $

      uft-flocker-ca --version

  This should return something like ``1.4.0``, showing you which version of the Flocker Client is installed.

.. _labs-installer-certs-directory:

Make a local directory for your cluster files
=============================================

The tools will create some configuration files and certificate files for your cluster.
It is convenient to keep these in a directory, so let's make a directory on your workstation like this:

.. prompt:: bash $

    mkdir -p ~/clusters/test
    cd ~/clusters/test

Now we'll put some files in this directory.

Get some nodes
==============

So now let's use the tools we've just installed to deploy and configure a Flocker cluster.

Run the following command in your ``~/clusters/test`` directory you made earlier:

.. prompt:: bash $

    mkdir terraform
    vim terraform/terraform.tfvars

.. note::

    In the following step, do not use a key (.pem file) which is protected by a passphrase.
    If necessary, generate and download a new keypair in the EC2 console.

Now paste the following variables into your ``terraform.tfvars`` file::

    # AWS keys
    aws_access_key = "your AWS access key"
    aws_secret_key = "your AWS secret key"

    # AWS region and zone
    aws_region = "region you want nodes deployed in e.g. us-east-1"
    aws_availability_zone = "zone you want nodes deployed in e.g. us-east-1a"

    # Key to authenticate to nodes via SSH
    aws_key_name = "name of EC2 keypair"
    private_key_path = "private key absolute path on machine running installer"

    # Instance types and number of nodes; total = agent_nodes + 1 (for master)
    aws_instance_type = "m3.large"
    agent_nodes = "2"

.. note::

    By default, the installer will launch one master node (where the control service runs) and two agent nodes (where volumes get attached and containers run).
    Please refer to the `AWS pricing guide <https://aws.amazon.com/ec2/pricing/>`_ to understand how much this will cost you.

Now run the following command to automatically provision some nodes.

.. prompt:: bash $

    uft-flocker-sample-files
    uft-flocker-get-nodes --ubuntu-aws

This step should take 30-40 seconds, and then you should see output like this::

    Apply complete! Resources: 10 added, 0 changed, 0 destroyed.

This should have created a pre-configured ``cluster.yml`` file in the current directory.

Now you have some nodes, it's time to install and configure Flocker on them!

Install and Configure Flocker
=============================

Run the following command:

.. prompt:: bash $

    uft-flocker-install cluster.yml && uft-flocker-config cluster.yml && uft-flocker-plugin-install cluster.yml

This step should take about 5 minutes, and will:

* install the OS packages on your nodes required to run Flocker, including Docker
* configure certificates, push them to your nodes, set up firewall rules for the control service
* start all the requisite Flocker services
* install the Flocker Docker plugin, so that you can control Flocker directly from the Docker CLI

Check that Flocker cluster is active
====================================

Try the Flocker CLI to check that all your nodes came up:

.. prompt:: bash $

    uft-flocker-volumes list-nodes
    uft-flocker-volumes list

You can see that there are no volumes yet.

Deploy and migrate a stateful app
=================================

Now you will deploy a highly sophisticated stateful app to test out Flocker.

We need to find out the IP addresses of our first two nodes.
Do this by running:

.. prompt:: bash $

   cat cluster.yml

Copy and paste the public IP addresses of the first two ``agent_nodes``.

In this example, ``demo`` is the name of the Flocker volume being created, which will map onto the Flocker volume being created.

.. prompt:: bash $

    NODE1="<node 1 public IP>"
    NODE2="<node 2 public IP>"
    KEY="<path on your machine to your .pem file>"
    chmod 0600 $KEY
    ssh -i $KEY root@$NODE1 docker run -d -v demo:/data --volume-driver=flocker --name=redis redis:latest
    ssh -i $KEY root@$NODE1 docker run -d -e USE_REDIS_HOST=redis --link redis:redis -p 80:80 --name=app binocarlos/moby-counter:latest
    uft-flocker-volumes list

This may take up to a minute since Flocker is provisioning and attaching an volume from the storage backend for the Flocker ``demo`` volume.
At the end you should see the volume created and attached to the first node.

Now visit ``http://<node 1 public IP>/`` and click around to add some Moby Docks to the screen.
Now let's stop the containers, then start the stateful app on another node in the cluster.

.. prompt:: bash $

    ssh -i $KEY root@$NODE1 docker rm -f app
    ssh -i $KEY root@$NODE1 docker rm -f redis
    ssh -i $KEY root@$NODE2 docker run -d -v demo:/data --volume-driver=flocker --name=redis redis:latest
    ssh -i $KEY root@$NODE2 docker run -d -e USE_REDIS_HOST=redis --link redis:redis -p 80:80 --name=app binocarlos/moby-counter:latest
    uft-flocker-volumes list

At the end you should see the volume has moved to the second node.

This may take up to a minute since Flocker is ensuring the volume is on the second host before starting the container.

Now visit ``http://<node 2 public IP>/`` and you’ll see that the location of the Moby Docks has been preserved.
Nice.

Cleaning up your cluster
========================

When you're done, if you want to clean up, run the following steps to clean up your volumes, your instances and your local files:

.. prompt:: bash $

    ssh -i $KEY root@$NODE2 docker rm -f app
    ssh -i $KEY root@$NODE2 docker rm -f redis
    uft-flocker-volumes list
    # Note the dataset id of the volume, then destroy it
    uft-flocker-volumes destroy --dataset=$DATASET_ID
    # Wait for the dataset to disappear from the list
    uft-flocker-volumes list
    # Once it's gone, go ahead and delete the nodes
    uft-flocker-destroy-nodes
    cd ~/clusters
    rm -rf test

.. note::

    If you wish to clean up your cluster manually, be sure to delete the instances that were created in your AWS console and the ``flocker_rules`` security group.

Further reading
===============

Now that you've installed your own Flocker cluster, you may want to learn more about Flocker:

* :ref:`Using Flocker <using>` (note that the ``flocker-deploy`` tool is installed on your system as ``uft-flocker-deploy``)
* :ref:`Flocker concepts <concepts>`
* :ref:`API reference <api>`
* :ref:`Flocker Docker plugin in detail <labs-docker-plugin>`

Or try some of our more experimental projects and integrations, including:

* :ref:`Volumes CLI <labs-volumes-cli>` and :ref:`GUI <labs-volumes-gui>`
* :ref:`Swarm <labs-swarm>`, :ref:`Compose <labs-compose>` and :ref:`Mesos/Marathon <labs-mesosphere>` integrations
