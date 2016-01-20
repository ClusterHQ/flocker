.. _installing-flocker-with-kubernetes:

===========================================
Manually Installing Flocker with Kubernetes
===========================================

#. Follow the :ref:`full-installation-with-kubernetes` steps.
#. Follow the :ref:`post-installation-configuration-with-kubernetes` steps, to configure authentication and your chosen backend.
   These steps also include the enablement of the control service and the agent services. 
#. Install :ref:`Kubernetes <manually-install-kubernetes>`.
#. Follow a tutorial to see how to control Flocker via Kubernetes.

.. _full-installation-with-kubernetes:

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

.. _post-installation-configuration-with-kubernetes:

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

.. _manually-install-kubernetes:

Manually Installing Kubernetes
==============================

Follow the `Manual Kubernetes installation <http://kubernetes.io/gettingstarted/>`_ guide on each of your nodes.

Next step
=========

Follow a tutorial to kick the tires on your Flocker cluster with Docker Swarm!

.. raw:: html

   <br/>
   <a href="index.html#kubernetes-tutorials" class="button">Try a Tutorial</a>
   <br/><br/>
