.. _installing-flocker:

==================
Installing Flocker
==================

There are several installation options with which you can get up and running with Flocker.

.. XXX The following sentence has been suppressed (FLOC 3577). TrueAbility has temporarily been taken offline to be updated.

.. You can also try Flocker without installation, either in our live hosted environment or on virtual machines using our Vagrant image.
.. For more information, see :ref:`get-started`.

.. _quick-start-installer:

Quick Start Flocker Installer
=============================

If you want to get started with Flocker quickly, but in your own environment, you can use the :ref:`Quick Start Flocker Installer <labs-installer>`.

.. note:: 
   The Installer is one of our :ref:`Labs projects <labs-projects>`, so is currently experimental.

.. _full-installation:

Full Installation
=================

To get the full Flocker functionality, the following installation steps will take you through installing the Flocker client, the Flocker node services, and the Flocker plugin for Docker:

.. XXX this introduction could be improved with an image. See FLOC-2077

.. toctree::
   :maxdepth: 3

   install-client
   install-node

Post Installation
=================

Once you have Flocker installed, you will need to complete the :ref:`post-installation-configuration`, starting with setting up authentication so the different parts of Flocker can communicate.

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :ref:`contribute`.

.. toctree::
   :hidden:

   setup-aws
   setup-rackspace
