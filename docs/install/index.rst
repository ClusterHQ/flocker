.. _installing-flocker:

==================
Installing Flocker
==================

There are several installation options with which you can get started with Flocker:

No Installation!
================

Take Flocker for a spin using a free, live demo environment. 
No installation is required, and it’s great for getting a hands-on introduction to what Flocker is all about.

* The live demo enviroment is hosted by ClusterHQ.
* The demo environment will include a fully-installed and configured 2-node Flocker cluster and CLI.
* You will have root access to this environment, and you can test Flocker however you want.
* Follow a step-by-step tutorial that will show you how to deploy a multi-node application and migrate its data volumes between hosts.
* To give you time to play, you’ll have access to the environment for 3 hours.

For more information, see the `Try Flocker`_ page.

Quick Start Flocker Installer
=============================

If you want to get started with Flocker quickly, but in your own environment, you can use the Installer.
The Installer is one of our :ref:`Labs projects <labs-projects>`, so is currently experimental.

* The Installer runs locally in a Docker container on your machine.
* It provisions nodes on AWS, and then installs Flocker, Docker, and the Flocker plugin for Docker.
* You can reconfigure the cluster at any time.
* The :ref:`Labs Installer <labs-installer>` documentation includes several tutorials to make it easy to set up and manage a Flocker cluster.

For more information, see the :ref:`Labs Installer <labs-installer>` page.

.. _vagrant-install:

Install Locally Using Vagrant
=============================

If you don’t want to use real servers, you can set up a cluster locally on virtual machines using our Vagrant image.

Our MongoDB tutorial uses both VirtualBox and Vagrant to install Flocker and Docker, and walks you through an end-to-end example of using Flocker to create an application.

For more information, see the :ref:`MongoDB tutorial <tutorial-mongo>`.

Full Installation
=================

These manual instructions take you through the full Flocker installation:

* You will install the Flocker Client on your local machine, which provides the command line tools to control the cluster.

  This includes the ``flocker-ca`` tool, which you will use to generate certificates for all the Flocker components.

* You will install the Flocker Node services, on any number of nodes in the cluster where your containers will run.

  The ``clusterhq-flocker-node`` package includes the Flocker agent software.

* The Flocker control service is installed on one of the agent hosts, or on a separate machine.
  
  The Flocker control service is also included in the ``clusterhq-flocker-node`` package, but is activated separately later in :ref:`enabling-control-service`.

.. XXX this introduction could be improved with an image. See FLOC-2077

.. toctree::
   :maxdepth: 2

   install-client
   install-node
   docker-plugin

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :ref:`contribute`.

.. toctree::
   :hidden:

   plugin-restrictions
   
.. _Try Flocker: https://clusterhq.com/flocker/try-flocker/live/
