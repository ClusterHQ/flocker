.. _installing-flocker-with-mesos:

===========================================
Manually Installing Flocker with Mesos
===========================================

#. Follow the :ref:`full-installation-with-mesos` steps, to install Flocker.
#. Follow the :ref:`post-installation-configuration-with-mesos` steps, to configure authentication and your chosen backend.
   These steps also include the enablement of the control service and the agent services. 
#. Install :ref:`Mesos <manually-install-mesos>`.
#. Follow a tutorial to see how to control Flocker via Mesos.

.. _full-installation-with-mesos:

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
   setup-rackspace

.. _post-installation-configuration-with-mesos:

.. include:: ../installation/index.rst
   :start-after: .. begin-body-configuring-flocker
   :end-before: .. end-body-configuring-flocker

.. toctree::
   :maxdepth: 2

   configuring-authentication
   generate-api-certificates
   enabling-control-service
   configuring-nodes-storage
   enabling-agent-service

.. _manually-install-mesos:

Manually Installing Mesos
==============================

Follow the `Manual Mesos installation <http://mesos.io/gettingstarted/>`_ guide on each of your nodes.

Next step
=========

:ref:`Try a tutorial <mesos-tutorials>` to kick the tyres on your Flocker cluster with Mesos!
