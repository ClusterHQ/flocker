.. _installing-flocker:

===================
Stand-alone Flocker
===================

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
   :maxdepth: 2

   install-client
   install-node

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :ref:`contribute`.

.. toctree::
   :hidden:

   setup-aws
   setup-rackspace

.. _post-installation-configuration:

Configuring Flocker
===================

Once you have installed Flocker you will need to complete the following configuration steps in order to start using your cluster:

.. toctree::
   :maxdepth: 2

   configuring-authentication
   generate-api-certificates
   generate-api-plugin
   enabling-control-service
   configuring-nodes-storage
   enabling-agent-service

.. _controlling-flocker:

Controlling Flocker
===================

You can control Flocker in a number of ways.
Find out which way is best for you.

Flocker lives on your nodes alongside Docker.
Each node where Docker is installed will have a Flocker agent as well.
The Flocker agents are controlled by the Flocker control service which is installed on just one node (usually a dedicated node).
The Flocker control service is controlled via API endpoints, either directly or indirectly.

You can control Flocker in the following ways:

* Using the Docker command line tools, via the Flocker plugin for Docker.
* Using the Flocker command line tools.
* Using the :ref:`Flocker API <api>` directly.

The following topics go into more detail about how you can control Flocker using the Flocker plugin for Docker, how you can use the Flocker CLI, and further information about how to administer Flocker:

.. toctree::
   :maxdepth: 2

   plugin/index
   cli/index
   administering/index

.. _concepts:

Flocker Concepts
================

.. toctree::
   :maxdepth: 2

   security
   architecture
   storage-profiles
   leases

