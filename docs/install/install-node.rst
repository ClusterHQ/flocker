.. _installing-flocker-node:

====================================
Installing the Flocker Node Services
====================================

It is possible to deploy Flocker in the cloud, on a number of different providers.

- :ref:`Using Amazon Web Services <aws-install>`
- :ref:`Using Rackspace <rackspace-install>`

It is also possible to install Flocker on any CentOS 7 or Ubuntu 14.04 machine.

- :ref:`Installing on CentOS 7 <centos-7-install>`
- :ref:`Installing on Ubuntu 14.04 <ubuntu-14.04-install>`

.. _centos-7-install:

Installing on CentOS 7
======================

.. note:: The following commands all need to be run as root on the machine where ``clusterhq-flocker-node`` will be running.

First, install the ``flocker-node`` package.
To install ``flocker-node`` on CentOS 7 you must install the RPM provided by the ClusterHQ repository.
The following commands will install the two repositories and the ``flocker-node`` package.
Paste them into a root console on the target node:

.. task:: install_flocker centos-7
   :prompt: [root@centos]#

Flocker's container management features depend on Docker.
Make sure `Docker (at least 1.8) is installed`_ and running.

Finally, you will need to run the ``flocker-ca`` tool that is installed as part of the CLI package.
This tool generates TLS certificates that are used to identify and authenticate the components of your cluster when they communicate, which you will need to copy over to your nodes.
Please see the :ref:`cluster authentication <authentication>` instructions.

.. _ubuntu-14.04-install:

Installing on Ubuntu 14.04
==========================

.. note:: The following commands all need to be run as root on the machine where ``clusterhq-flocker-node`` will be running.

Setup the pre-requisite repositories and install the ``clusterhq-flocker-node`` package.

.. task:: install_flocker ubuntu-14.04
   :prompt: [root@ubuntu]#

Flocker's container management features depend on Docker.
Make sure `Docker (at least 1.8) is installed`_  and running.

Finally, you will need to run the ``flocker-ca`` tool that is installed as part of the CLI package.
This tool generates TLS certificates that are used to identify and authenticate the components of your cluster when they communicate, which you will need to copy over to your nodes.
Please continue onto the next section, with the cluster authentication instructions.

Next Step
=========

In the next step :ref:`the node control and agent services will be configured and started<post-installation-configuration>`.

.. _Docker (at least 1.8) is installed: https://docs.docker.com/installation/
