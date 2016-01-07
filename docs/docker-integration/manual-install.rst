.. _installing-flocker-with-docker:

=============================================
Manually Installing Flocker with Docker Swarm
=============================================

Manually Installing Flocker
===========================

#. Follow the :ref:`full-installation-with-docker` steps. 
   This includes a step to install the **Flocker plugin for Docker**, which is required for Docker Swarm integration.
#. Follow the :ref:`post-installation-configuration-with-docker` steps.
#. Follow the :ref:`controlling-flocker-with-docker` steps.

.. _full-installation-with-docker:

.. include:: ../installation/index.rst
   :start-after: .. begin-body-full-installation
   :end-before: .. end-body-full-installation

.. _post-installation-configuration-with-docker:

.. include:: ../installation/index.rst
   :start-after: .. begin-body-configuring-flocker
   :end-before: .. end-body-configuring-flocker

.. _controlling-flocker-with-docker:

.. include:: ../installation/index.rst
   :start-after: .. begin-body-controlling-flocker
   :end-before: .. end-body-controlling-flocker

Manually Installing Docker Swarm
================================

Follow the `Manual Docker Swarm installation <https://docs.docker.com/swarm/install-manual/>`_ guide on your nodes.

Next steps
==========

:ref:`Try a tutorial <docker-tutorials>` to kick the tyres on your Flocker cluster with Docker Swarm!
