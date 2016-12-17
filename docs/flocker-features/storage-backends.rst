.. _supported-backends:

==================
Supported Backends
==================

The following backends are supported by Flocker.
These have either been provided by ClusterHQ, or are supported by our community partners.

Each backend page listed below provides configuration details for setting up your backend.
Please note that when you have completed the configuration of your chosen backend, you may need to return to the configuration steps in order to start using Flocker.
For more information, see :ref:`backends-next-steps`.

ClusterHQ supported drivers
===========================

* :ref:`aws-dataset-backend`
* :ref:`gce-dataset-backend`
* :ref:`openstack-dataset-backend`
* :ref:`loopback-dataset-backend`

.. toctree::
   :hidden:

   aws-configuration
   gce-configuration
   openstack-configuration
   loopback-configuration

Community supported drivers
===========================

* :ref:`convergeio-backend`
* :ref:`dell-dataset-backend`
* :ref:`emc-dataset-backend`
* :ref:`hedvig-backend`
* :ref:`huawei-backend`
* :ref:`netapp-backend`
* :ref:`nexenta-backend`
* :ref:`open-vstorage-backend`
* :ref:`saratogaspeed-backend`
* :ref:`vmware-backend`
* :ref:`coprhd-backend`
* :ref:`pure-storage-backend`
* :ref:`kaminario-backend`

.. toctree::
   :hidden:

   convergeio-configuration
   dell-configuration
   emc-configuration
   hedvig-configuration
   huawei-configuration
   netapp-configuration
   nexenta-configuration
   open-vstorage-configuration
   saratogaspeed-configuration
   vmware-configuration
   coprhd-configuration
   pure-storage-configuration
   kaminario-configuration

Flocker supports pluggable storage backends.
Any storage system that is able to present itself as a network-based block device can serve as the underlying storage for a Docker data volume managed by Flocker.
If the storage backend you are looking for is not currently supported by Flocker, you can consider :ref:`contributing it <build-flocker-driver>`.

.. _backends-next-steps:

Next Step
=========

If you have configured a backend as part of the Flocker configuration process, you will now need to return to complete the configuration steps before you can use Flocker.

The links below will return you to the final step of your configuration process:

* :ref:`Enabling the Flocker Agent Service for the Docker Integration <enabling-agent-service-docker>`
* :ref:`Enabling the Flocker Agent Service for the Kubernetes Integration <enabling-agent-service-kubernetes>`
* :ref:`Enabling the Flocker Agent Service for an Integration of Flocker with Other Systems <enabling-agent-service-standalone-flocker>`
