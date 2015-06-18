.. _labs-installer:

======================
Experimental installer
======================

The experimental installer makes installing Flocker as easy as copying and editing a single YAML file with your node configuration and then running two or three commands to create the certificates and install the software on your nodes.

It also supports deploying the :ref:`Flocker Docker plugin <labs-docker-plugin>` onto the same set of nodes.

See the :ref:`official Flocker install instructions <installflocker>` for the full long-form installation instructions.

The installer is part of the ``unofficial-flocker-tools`` package, so we will install that to begin with.

.. _labs-installing-unofficial-flocker-tools:

Installing Unofficial Flocker Tools
===================================

* Install ``flocker-cli <installing-flocker-cli>`` for your platform.
* OS packages:

  * Ubuntu/Debian: ``sudo apt-get install -y python-pip build-essential libssl-dev libffi-dev python-dev``
  * RHEL/Fedora: ``sudo yum install -y python-pip gcc libffi-devel python-devel openssl-devel``

Using pip, you can install ``unofficial-flocker-tools`` straight from GitHub:

.. prompt:: bash $

    sudo pip install git+https://github.com/clusterhq/unofficial-flocker-tools.git

This will install the following tools on your machine:

* ``flocker-sample-files``: put some sample ``cluster.yml`` files in the current directory
* ``flocker-config``: generate certificates and push them
* ``flocker-install``: install Flocker OS packages on target nodes
* ``flocker-plugin-install``: install experimental Docker and the :ref:`Flocker Docker plugin <labs-docker-plugin>` on target nodes
* ``flocker-tutorial``: print out some instructions on how to test the cluster with ``curl`` commands
* ``flocker-volumes``: an experimental volumes CLI

.. _labs-installer-certs-directory:

Make a directory for your cluster
=================================

The tools will create some certificate files for your cluster.
It is convenient to keep these in a directory, so for example, do something like this:

.. prompt:: bash $

    mkdir -p ~/clusters/test
    cd ~/clusters/test

Later commands in this document will put some files in this directory.

Get some nodes
==============

So now let's use the tools we've just installed to deploy and configure a Flocker cluster quickly!

Provision some machines, somehow.
Use Ubuntu 14.04 or CentOS 7.

* Use Amazon EC2 if you want to use our EBS backend (note VMs must be deployed in the same AZ).
* Use an OpenStack deployment (e.g. Rackspace, private cloud) if you want to try our OpenStack backend.

..warning::
    Make sure you can log into the nodes as **root** with a private key. (e.g. on ubuntu on AWS, `sudo cp .ssh/authorized_keys /root/.ssh/authorized_keys`)

You may want to pick a node to be the control node and give it a DNS name (if you do this, set up an A record for it with your DNS provider). Using a DNS name is optional, you can also just use its IP address.

cluster.yml
===========

There are some example configuration files that correspond to the backend Flocker will use - base your cluster.yml on one of these files:

* [AWS EBS](cluster.yml.ebs.sample)
* [Openstack Cinder](cluster.yml.openstack.sample)
* [ZFS](cluster.yml.zfs.sample)

for example:

```
mv cluster.yml.ebs.sample cluster.yml
vim cluster.yml # customize for your cluster
```

## install

```
./install.py cluster.yml
```

this will install the packages on your nodes

at this point you will need to manually install the latest (highest numbered) packages from http://build.clusterhq.com/results/omnibus/master/ onto your nodes as well.


## deploy

```
./deploy.py cluster.yml
```

this will configure certificates, push them to your nodes, and set up firewall rules for the control service

..warning::
    On AWS, you'll need to add a firewall rule for TCP port 4523 and 4524 if you want to access the control service/API remotely.

## plugin

```
./plugin.py cluster.yml
```

this will configure api certificates for the docker-plugin and push them to your nodes - it will name them `/etc/flocker/plugin.{crt,key}`

it will git clone the plugin repo, checkout a branch and install the dependencies (pip install) and write a service file (upstart/systemd) for the plugin

it will also download a customized docker binary that supports the `--volume-driver` flag and restart the docker service.

The environment variables that control this are:

 * `DOCKER_BINARY_URL` - the url to download a customized docker binary from
 * `DOCKER_SERVICE_NAME` - the name of the service docker is installed with (docker, docker.io etc)
 * `PLUGIN_REPO` - the repo to install the docker plugin from
 * `PLUGIN_BRANCH` - the branch of the plugin repo to use

## tutorial

```
./tutorial.py cluster.yml
```

this will print out a tutorial customized to your deployment.

## notes

* you need to ensure that machines can be SSH'd into as root
* you need a private key to access the machines - you can configure this in the `private_key_path` of cluster.yml

