.. Single Source Instructions

==============
Labs Installer
==============

.. begin-body-labs-installer

.. raw:: html

   <img src="_images/experimental.png" style="height:25px; padding:2px 4px; margin-left:20px; border:1px solid #ddd;" title="Experimental (labs project)"> This is an experimental project that has been developed to less rigorous quality and testing standards than the mainline Flocker distribution. It has not been built with production-readiness in mind.

.. raw:: html

   <div style="display:none;">

.. image:: images/experimental.png

.. raw:: html

   </div>
   
This document guides you through setting up a Flocker cluster and gives a simple example of deploying and moving around a service which includes a stateful container.

Key Points
==========

* Flocker is a clustered container data volume manager.
  This means it runs on a cluster (a group) of machines, and connects containers to data volumes so that containers which store data, such as databases, keep their data as they move around the cluster.
* Flocker is installed on servers, which you must provision, for example on cloud infrastructure.
* It works with other container tools, such as Swarm, Compose and Mesos/Marathon.

Architecture
============

This diagram shows you what you are about to set up.

.. image:: ../images/install-architecture.png

.. Source file is at "Engineering/Labs/flocker architecture" https://drive.google.com/open?id=0B3gop2KayxkVbmNBR2Jrbk0zYmM

* Installer runs in a Docker container on your local machine.
* You give the installer your cloud infrastructure credentials.
* Installer provisions servers for you, and it writes a ``cluster.yml`` in your cluster directory containing the addresses of the servers.
* You run the installer on the ``cluster.yml``.
* Installer creates certificates for you, saves them in your cluster directory, installs Flocker and certificates on servers, and starts Flocker.
* You can now interact with your Flocker cluster using the ``docker`` CLI on the nodes, or locally by using the ``uft-flocker-deploy`` tool or the ``uft-flocker-volumes`` tool.

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

Other configurations (for example, CentOS or OpenStack) are possible via the :ref:`manual Flocker installation docs <installing-standalone-flocker>`.

You may also be interested in the long-form documentation if you like to see exactly how things are done, or if you're automating setting up Flocker within your own configuration management system.

.. note::

    If you get an error response from any of the commands in this guide, please `report a bug <https://github.com/clusterhq/unofficial-flocker-tools/issues>`_, pasting the ``install-log.txt`` file you will find in the current directory.

Get Started
===========

.. toctree::
   :maxdepth: 1
   
   ../installation/installer-getstarted
   ../installation/installer-tutorial
   ../installation/cluster-cleanup

.. end-body-labs-installer
