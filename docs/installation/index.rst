.. Single Source Instructions

==================
Installing Flocker
==================

.. begin-body-full-installation

1. Installing Flocker
=====================

To get the full Flocker functionality, the following installation steps will take you through installing the Flocker client and the Flocker node services.

.. XXX this introduction could be improved with an image. See FLOC-2077

.. note:: If you're interested in developing Flocker (as opposed to simply using it), see :ref:`contribute`.

.. end-body-full-installation

.. toctree::
   :maxdepth: 2

   ../installation/install-client
   ../installation/install-node

.. toctree::
   :hidden:

   ../installation/setup-aws
   ../installation/setup-gce
   ../installation/setup-rackspace

.. begin-body-configuring-flocker

2. Configuring Flocker
======================

Once you have installed Flocker you will need to complete the following configuration steps in order to start using your cluster:

.. end-body-configuring-flocker

.. toctree::
   :maxdepth: 2

   ../installation/configuring-authentication
   ../installation/generate-api-certificates
   ../installation/enabling-control-service
   ../installation/configuring-nodes-storage
   ../installation/enabling-agent-service
