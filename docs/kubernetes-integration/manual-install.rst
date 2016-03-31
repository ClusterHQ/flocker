.. _installing-flocker-with-kubernetes:

===========================================
Manually Installing Flocker with Kubernetes
===========================================

#. :ref:`Install Flocker <full-installation-with-kubernetes>`. 
   Follow these steps to install Flocker.
#. :ref:`Configure Flocker <post-installation-configuration-with-kubernetes>`.
   Follow these steps to configure authentication and your chosen backend.
   You will also enable the control service and the agent services. 
#. :ref:`Install Kubernetes <manually-install-kubernetes>`.
#. Follow a :ref:`tutorial <link-to-kubernetes-tutorials>` to see how to control Flocker via Kubernetes.

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
   setup-gce
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

3. Installing Kubernetes
========================

Follow the `Kubernetes installation <http://kubernetes.io/gettingstarted/>`_ guide on each of your nodes.

.. _link-to-kubernetes-tutorials:

4. Tutorial
===========

Follow a tutorial to kick the tires on your Flocker cluster with Docker Swarm!

.. raw:: html

   <br/>
   <a href="index.html#kubernetes-tutorials" class="button">Try a Tutorial</a>
   <br/><br/>
