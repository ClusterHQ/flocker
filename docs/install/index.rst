.. _installing-flocker:

==================
Installing Flocker
==================

There are several installation options with which you can get up and running with Flocker.

.. _quick-start-installer:

Quick Start Flocker Installer
=============================

If you want to get started with Flocker quickly, but in your own environment, you can use the :ref:`Quick Start Flocker Installer <labs-installer>`.

.. note:: 
   The Installer is one of our :ref:`Labs projects <labs-projects>`, so is currently experimental.

.. _full-installation:

Full Installation
=================

To get the full Flocker functionality, the following installation steps will take you through installing the :ref:`Flocker client <installing-flocker-cli>`, the :ref:`Flocker node services <installing-flocker-node>`.

If you want to install the :ref:`Flocker plugin for Docker <docker-plugin>`, this is included in the Flocker node services instructions:

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
