=======================
Introduction to Flocker
=======================

What is Flocker?
================

Flocker is an open-source Container Data Volume Manager for your Dockerized applications.

By providing tools for data migrations, Flocker gives ops teams the tools they need to run containerized stateful services like databases in production.

Unlike a Docker data volume which is tied to a single server, a Flocker data volume, called a dataset, is portable and can be used with any container, no matter where that container is running.

Flocker manages Docker containers and data volumes together.
When you use Flocker to manage your stateful microservice, your volumes will follow your containers when they move between different hosts in your cluster.

You can also use Flocker to manage only your volumes, while continuing to manage your containers however you choose.

.. image:: images/flocker-v-native-containers.svg
   :alt: Migrating data: Native Docker versus Flocker.
         In native Docker, when a container moves, its data volume stays in place.
		 Database starts on a new server without any data.
		 When using Flocker, when a container moves, the data volume moves with it.
		 Your database gets to keep its data!

Flocker Basics
==============

Flocker works by exposing a simple :ref:`REST API<api>` on its Control Service.
The Flocker Control Service communicates with Flocker Agents running on each node in the cluster to carry out commands.

To interact with the Flocker API you can use the :ref:`Flocker CLI<cli>`, or access it directly in popular programming languages like Go, Python and Ruby.

With the Flocker API or CLI you can:

* Deploy a multi-container application to multiple hosts
* Move containers between hosts along with their volumes
* Attach and detach data volumes from containers as they change hosts
* Migrate local data volumes between servers (currently Experimental)

Flocker supports block-based shared storage such as Amazon EBS, Rackspace Cloud Block Storage, and EMC ScaleIO, as well as local storage (currently Experimental using our ZFS storage backend) so you can choose the storage backend that is best for your application.

.. XXX add link to choosing the best storage for your application marketing page (yet to be published)

.. _flocker-containers-architecture:

.. image:: images/flocker-architecture.svg
   :alt: Flocker architecture with shared storage backend.
         The Flocker Control Service and containers hosts can run on a VM or bare metal servers.
		 The Flocker Agent running on each host speaks to the shared storage backend to create and moutn volumes to individual containers.

Flocker also has planned integrations with Docker itself, major orchestration tools such as Docker Swarm, Kubernetes and Apache Mesos.
More information on these integrations is :ref:`available in the Labs section <labs-projects>`.

.. XXX add link to 3rd party orchestration docs. See FLOC 2229

.. _supported-operating-systems:

Supported Operating Systems
===========================

* CentOS 7
* Ubuntu 14.04
* Ubuntu 15.04 (Command Line only)
* OS X (Command Line only)

Supported Cloud Providers
=========================

* AWS
* Rackspace

Supported Storage Backends
==========================

* AWS EBS
* Rackspace Cloud Block Storage
* Anything that supports the OpenStack Cinder API
* EMC ScaleIO
* EMC XtremIO
* Local storage using our ZFS driver (currently Experimental)
