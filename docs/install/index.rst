.. _installing-flocker:

==================
Installing Flocker
==================

Quick Start
===========

Want to get started with Flocker quickly?
Try the :ref:`Installer <labs-installer>`.

* It makes it easy to set up and manage a Flocker cluster.
* It runs inside a Docker container on your local machine.

:ref:`Click here to proceed with the automatic installer <labs-installer>`.

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
