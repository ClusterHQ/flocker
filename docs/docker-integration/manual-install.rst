.. _installing-flocker-with-docker:

=============================================
Manually Installing Flocker with Docker Swarm
=============================================

#. :ref:`Install Flocker <full-installation-with-docker>`. 
   Follow these steps to install Flocker.
#. :ref:`Configure Flocker <post-installation-configuration-with-docker>`.
   Follow these steps to configure authentication and your chosen backend.
   You will also enable the control service, the agent services, and the plugin. 
#. :ref:`Install Docker Swarm <manually-install-swarm>`.
#. Follow a :ref:`tutorial <link-to-docker-tutorials>` to see how to control Flocker via Docker Swarm.

.. _full-installation-with-docker:

.. include:: ../installation/index.rst
   :start-after: .. begin-body-full-installation
   :end-before: .. end-body-full-installation

.. toctree::
   :maxdepth: 2

   install-client
   install-node

.. toctree::
   :hidden:
   
   setup-aws
   setup-gce
   setup-rackspace

.. _post-installation-configuration-with-docker:

.. include:: ../installation/index.rst
   :start-after: .. begin-body-configuring-flocker
   :end-before: .. end-body-configuring-flocker

.. toctree::
   :maxdepth: 2

   configuring-authentication
   generate-api-certificates
   generate-api-plugin
   enabling-control-service
   configuring-nodes-storage
   enabling-agent-service

.. _manually-install-swarm:

3. Installing Docker Swarm
==========================

Follow the `Docker Swarm installation <https://docs.docker.com/swarm/install-manual/>`_ guide on each of your nodes.

.. _link-to-docker-tutorials:

4. Tutorial
===========

Follow a tutorial to kick the tires on your Flocker cluster with Docker Swarm!

.. raw:: html

   <br/>
   <a href="tutorial-swarm-compose.html" class="button">Try a Tutorial</a>
   <br/><br/>
