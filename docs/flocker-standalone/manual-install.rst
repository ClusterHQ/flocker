.. _installing-standalone-flocker:

===========================
Manually Installing Flocker
===========================

#. Follow the :ref:`full-installation-standalone-flocker` steps.
#. Follow the :ref:`post-installation-configuration-standalone-flocker` steps, to configure authentication and your chosen backend.
   These steps also include the enablement of the control service and the agent services. 

.. _full-installation-standalone-flocker:

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

.. _post-installation-configuration-standalone-flocker:

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
