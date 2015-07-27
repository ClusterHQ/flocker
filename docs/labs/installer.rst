.. _labs-installer:

======================
Experimental installer
======================

The experimental installer makes installing Flocker as easy as copying and editing a single YAML file with your node configuration and then running two or three commands to create the certificates and install the software on your nodes.

It also supports deploying the :ref:`Flocker Docker plugin <labs-docker-plugin>` onto the same set of nodes.

See the :ref:`official Flocker install instructions <installing-flocker>` for the full long-form installation instructions.

The installer is part of the `Unofficial Flocker Tools <https://github.com/clusterhq/unofficial-flocker-tools>`_ repository, so we will install that to begin with.

.. _labs-installing-unofficial-flocker-tools:

Installing Unofficial Flocker Tools
===================================

First we install the tools **on your local machine**.

* Install :ref:`the Flocker CLI <installing-flocker-cli>` for your platform (in particular, we need the ``flocker-ca`` tool).
* OS packages:

  * Ubuntu/Debian:

    .. prompt:: bash $

        sudo apt-get install -y python-pip build-essential libssl-dev libffi-dev python-dev

  * RHEL/CentOS/Fedora:

    .. prompt:: bash $

        sudo yum install -y python-pip gcc libffi-devel python-devel openssl-devel

Using ``pip``, you can install ``unofficial-flocker-tools`` straight from GitHub:

.. prompt:: bash $

    sudo pip install git+https://github.com/clusterhq/unofficial-flocker-tools.git

If you prefer to use a ``virtualenv``, just activate one and then run ``pip`` without ``sudo``.

This will install the following tools on your machine:

* ``flocker-sample-files``: put some sample ``cluster.yml`` files in the current directory
* ``flocker-config``: generate certificates and push them
* ``flocker-install``: install Flocker OS packages on target nodes
* ``flocker-plugin-install``: install experimental Docker and the :ref:`Flocker Docker plugin <labs-docker-plugin>` on target nodes
* ``flocker-tutorial``: print out some instructions on how to test the cluster with ``curl`` commands
* ``flocker-volumes``: an experimental volumes CLI

.. _labs-installer-certs-directory:

Make a local directory for your cluster files
=============================================

The tools will create some configuration files and certificate files for your cluster.
It is convenient to keep these in a directory, so let's make a directory on your workstation (assuming Linux or OS X) like this:

.. prompt:: bash $

    mkdir -p ~/clusters/test
    cd ~/clusters/test

Later commands in this document will put some files in this directory.

Get some nodes
==============

So now let's use the tools we've just installed to deploy and configure a Flocker cluster quickly!

Provision some machines on AWS or an OpenStack deployment (e.g. Rackspace).
Use Ubuntu 14.04 or CentOS 7.
We recommend Ubuntu 14.04 if you want to try the Flocker Docker plugin.

Make sure you create the servers a reasonable amount of disk space, since Docker images will be stored on the VM root disk itself.

* Use Amazon EC2 if you want to use our EBS backend (note VMs must be deployed in the same AZ).
* Use an OpenStack deployment (e.g. Rackspace, private cloud) if you want to try our OpenStack backend (VMs must be deployed in the same region).

.. warning::
    Make sure you can log into the nodes as **root** with a private key. (e.g. on Ubuntu on AWS, ``sudo cp .ssh/authorized_keys /root/.ssh/authorized_keys``)

You may want to pick a node to be the control node and give it a DNS name (if you do this, set up an A record for it with your DNS provider). Using a DNS name is optional, you can also just use its IP address.

cluster.yml
===========

Run the following command in your ``~/clusters/test`` directory you made earlier:

.. prompt:: bash $

    flocker-sample-files

This will create some sample configuration files that correspond to the backend Flocker will use - base your ``cluster.yml`` on one of these files:

* AWS EBS: ``cluster.yml.ebs.sample``
* OpenStack (including Rackspace): ``cluster.yml.openstack.sample``

.. * ZFS: ``cluster.yml.zfs.sample`` XXX put this back when https://github.com/ClusterHQ/unofficial-flocker-tools/issues/2 lands

Choose the one that's appropriate for you, and then customize it with your choice of text editor.
For example:

.. prompt:: bash $

    mv cluster.yml.ebs.sample cluster.yml
    vim cluster.yml # customize for your cluster

.. note::

    You need a private key which can access the machines **as root** - you can configure this in the ``private_key_path`` of ``cluster.yml``.

Install
=======

From the directory where your ``cluster.yml`` file is now, run the following command:

.. prompt:: bash $

    flocker-install cluster.yml

This will install the OS packages on your nodes required to run Flocker.
Flocker is not ready to run yet, we still need to do some certificate management.


Configure (certificates)
========================

From the directory where your ``cluster.yml`` file is now, run the following command:

.. prompt:: bash $

    flocker-config cluster.yml

This will configure certificates, push them to your nodes, and set up firewall rules for the control service.

.. warning::
    On AWS, you also need to add a firewall rule allowing traffic for TCP port 4523 and 4524 if you want to access the control service or API remotely.

Install Flocker Docker plugin (optional)
========================================

If you want to install the :ref:`Flocker Docker plugin <labs-docker-plugin>` then follow these steps.
Currently this has only been tested on Ubuntu 14.04.

Please keep in mind :ref:`this note on architecture <labs-architecture-note>`.

From the directory where your ``cluster.yml`` file is now, run the following command:

.. prompt:: bash $

    flocker-plugin-install cluster.yml

This will configure API certificates for the Flocker Docker plugin and push them to your nodes - it will name them ``/etc/flocker/plugin.{crt,key}`` on the nodes.

It will install the Flocker Docker plugin, and write a service file (``upstart``/``systemd``) for the plugin (as described in the :ref:`manual installation instructions for the Flocker Docker plugin <labs-docker-plugin>`.

It will also download and install an experimental Docker binary that supports the ``--volume-driver`` flag and restart the Docker service.

It supports several optional environment variables:

* ``DOCKER_BINARY_URL`` - the URL to download a customized Docker binary from
* ``DOCKER_SERVICE_NAME`` - the name of the service docker is installed with (``docker``, ``docker.io`` etc)
* ``PLUGIN_REPO`` - the GitHub repository URL to install the docker plugin from
* ``PLUGIN_BRANCH`` - the branch of the plugin repository to use

Once you've installed the Flocker Docker plugin, check out the experimental :ref:`volumes CLI <labs-volumes-cli>` and :ref:`GUI <labs-volumes-gui>`, and the :ref:`Swarm <labs-swarm>` and :ref:`Compose <labs-compose>` integrations.

Print a simple tutorial
=======================

.. prompt:: bash $

    flocker-tutorial cluster.yml

This will print out a short tutorial on exercising the Flocker volumes and containers APIs, customized to your deployment.

Known limitations
=================

* This installer doesn't yet do the key management required for the ZFS backend to operate.
  See `#2 <https://github.com/ClusterHQ/unofficial-flocker-tools/issues/2>`_.
