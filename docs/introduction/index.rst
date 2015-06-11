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

.. image:: images/flocker-v-native-containers.svg
   :alt: Migrating data: Native Docker versus Flocker.
         In native Docker, when a container moves, its data volume stays in place.
		 Database starts on a new server without any data.
		 When using Flocker, when a container moves, the data volume moves with it.
		 Your database gets to keep its data!

Controlling Flocker
===================

Flocker works by exposing a simple REST API on its Control Service.
The Flocker Control Service communicates with Flocker Agents running on each node in the cluster to carry out commands.

To interact with the Flocker API you can use the Flocker CLI, or access it directly in popular programming languages like Go, Python and Ruby.

With the Flocker API or CLI you can:

* Deploy a multi-container application to multi-hosts
* Move containers between hosts
* Attach and detach data volumes from containers as they change hosts
* Migrate local data volumes between servers (currently Experimental)

Storage and Orchestration
=========================

Flocker supports block-based shared storage such as Amazon EBS, Rackspace Cloud Block Storage, and EMC ScaleIO, as well as local storage (currently Experimental using our ZFS storage backend) so you can choose the storage backend that is best for your application.

.. XXX add link to choosing the best storage for your application marketing page (yet to be published)

.. image:: images/flocker-architecture.svg
   :alt: Flocker architecture with shared storage backend.
         The Flocker Control Service and containers hosts can run on a VM or bare metal servers.
		 The Flocker Agent running on each host speaks to the shared storage backend to create and moutn volumes to individual containers.

Flocker also has planned integration with major orchestration tools such as Docker Swarm, Kubernetes and Apache Mesos. More information on this integration is coming soon.

.. XXX add link to 3rd party orchestration docs. See FLOC 2229

Motivation for Building Flocker
===============================
Flocker lets you move your Docker containers and their data together between Linux hosts.
This means that you can run your databases, queues and key-value stores in Docker and move them around as easily as the rest of your app.
Even stateless apps depend on many stateful services and currently running these services in Docker containers in production is nearly impossible.
Flocker aims to solve this problem by providing an orchestration framework that allows you to port both your stateful and stateless containers between environments.

Docker allows for multiple isolated, reproducible application environments on a single node: "containers".
Application state can be stored on a local disk in "volumes" attached to containers.
And containers can talk to each other and the external world via specified ports.

But what happens if you have more than one node?
How does application state work if you move containers around?
Flocker solves this problem by moving your volumes to where your applications are.

The diagram below provides a high level representation of how Flocker addresses these questions.

.. image:: images/flocker-architecture-diagram.jpg
   :alt: Containers run on physical nodes with Local Storage (ZFS).
         Flocker's proxying layer allows you to communicate with containers by routing traffic to any node.
         Filesystem state gets moved around with ZFS.

Future versions of Flocker will also support network block storage like EBS and OpenStack Cinder.
