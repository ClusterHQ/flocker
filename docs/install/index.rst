.. _installing-flocker:

==================
Installing Flocker
==================

There are several installation options with which you can get up and running with Flocker:

Quick Start Flocker Installer
=============================

If you want to get started with Flocker quickly, but in your own environment, you can use the Installer.
The Installer is one of our :ref:`Labs projects <labs-projects>`, so is currently experimental.

* The Installer runs locally in a Docker container on your machine.
* It provisions nodes on AWS, and then installs Flocker, Docker, and the Flocker plugin for Docker.
* You can reconfigure the cluster at any time.
* The :ref:`Labs Installer <labs-installer>` documentation includes several tutorials to make it easy to set up and manage a Flocker cluster.

For more information, see the :ref:`Labs Installer <labs-installer>` page.

Full Installation
=================

For a full Flocker installation, including the Flocker plugin for Docker, the following manual instructions take you through everything you need to do:

.. XXX this introduction could be improved with an image. See FLOC-2077

.. toctree::
   :maxdepth: 1

   install-client
   install-node
   docker-plugin

Once you have Flocker installed, you will need to complete the :ref:`post-installation-configuration` steps in order to use Flocker.

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :ref:`contribute`.

.. toctree::
   :hidden:

   plugin-restrictions
   
.. _Try Flocker: https://clusterhq.com/flocker/try-flocker/live/
