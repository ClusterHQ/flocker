.. _installing-flocker-with-docker:

=============================================
Manually Installing Flocker with Docker Swarm
=============================================

#. Follow the :ref:`full-installation-with-docker` steps, to install Flocker and the :ref:`Flocker plugin for Docker <plugin>`.
   The plugin is required for Docker Swarm integration.
#. Follow the :ref:`post-installation-configuration-with-docker` steps, to configure authentication and your chosen backend.
   These steps also include the enablement of the control service, the agent services, and the plugin. 
#. Install Swarm manually.
#. Follow a tutorial to see how to control Flocker via Swarm.

.. _full-installation-with-docker:

.. include:: ../installation/index.rst
   :start-after: .. begin-body-full-installation
   :end-before: .. end-body-full-installation

.. _post-installation-configuration-with-docker:

.. include:: ../installation/index.rst
   :start-after: .. begin-body-configuring-flocker-docker
   :end-before: .. end-body-configuring-flocker-docker

Manually Installing Docker Swarm
================================

Follow the `Manual Docker Swarm installation <https://docs.docker.com/swarm/install-manual/>`_ guide on your nodes.

Next steps
==========

:ref:`Try a tutorial <docker-tutorials>` to kick the tyres on your Flocker cluster with Docker Swarm!
