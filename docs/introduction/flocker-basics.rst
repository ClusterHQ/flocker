==============
Flocker Basics
==============

Flocker works by exposing a simple :ref:`REST API<api>` on its control service.
The :ref:`Flocker control service <control-service>` communicates with Flocker Agents running on each node in the cluster to carry out commands.

To interact with the Flocker API you can use the :ref:`Flocker CLI<cli>`, or access it directly in popular programming languages like Go, Python and Ruby.

With the Flocker API or CLI you can:

* Deploy a multi-container application to multiple hosts
* Move containers between hosts along with their volumes
* Attach and detach data volumes from containers as they change hosts
* Migrate local data volumes between servers (currently Experimental)

Flocker supports block-based shared storage such as Amazon EBS, Rackspace Cloud Block Storage, and EMC ScaleIO, as well as local storage, so you can choose any of :ref:`the available storage backends <storage-backends>` that best suit your application.

.. XXX add link to choosing the best storage for your application marketing page (yet to be published)

.. _flocker-containers-architecture:

.. image:: images/flocker-architecture.svg
   :alt: Flocker architecture with shared storage backend.
         The Flocker Control Service and containers hosts can run on a VM or bare metal servers.
		 The Flocker Agent running on each host speaks to the shared storage backend to create and moutn volumes to individual containers.
