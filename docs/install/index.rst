.. _installing-flocker:

==================
Installing Flocker
==================

There are several installation options with which you can get started with Flocker:

No Installation!
================

Take Flocker for a spin using a free, live demo environment. 
No installation is required, and it’s great for understanding what Flocker’s all about.

* The live demo enviroment is hosted by ClusterHQ.
* The demo environment will include a fully-installed and configured 2-node Flocker cluster and CLI.
* You will have root access to this environment, and you can test Flocker however you want.
* Follow a step-by-step tutorial that will show you how to deploy a multi-node application and migrate its data volumes between hosts.
* To give you time to play, you’ll have access to the environment for 3 hours.

For more information, see the `Try Flocker`_ page.

Quick Start
===========

Want to get started with Flocker quickly?
You can try the Labs Installer.

* It makes it easy to set up and manage a Flocker cluster.
* It runs inside a Docker container on your local machine.
* The :ref:`Flocker plugin for Docker <using-docker-plugin>` is installed.

:ref:`Try the Labs installer <labs-installer>`.

If you'd rather install Flocker manually, read on.

Manual Installation
===================

The Flocker Client is installed on your local machine and provides command line tools to control the cluster.
This also includes the ``flocker-ca`` tool, which you use to generate certificates for all the Flocker components.

The Flocker agents are installed on any number of nodes in the cluster where your containers will run.
The agent software is included in the ``clusterhq-flocker-node`` package.

There is also a Flocker control service which you must install on one of the agent hosts, or on a separate machine.
The control service is also included in the ``clusterhq-flocker-node`` package, but is activated separately later in these installation instructions.

.. note:: The agents and control service are pre-installed by the :ref:`Vagrant configuration in the tutorial <tutvagrant>`.

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :ref:`contribute`.

This document will describe how to install the client locally and install the agents and control service on cloud infrastructure.
It also describes how to get Vagrant nodes started which already have these services running.

.. XXX We will improve this introduction with an image. See FLOC-2077

.. toctree::
   :maxdepth: 2

   install-client
   install-node
   docker-plugin

.. toctree::
   :hidden:

   plugin-restrictions
   
.. _Try Flocker: https://clusterhq.com/flocker/try-flocker/live/
