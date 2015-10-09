.. _introduction:

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
To use Flocker to manage your volumes while tools like Docker, Docker Swarm or Mesos manage your containers, you can :ref:`use the Flocker plugin for Docker <docker-plugin>`.

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

Flocker supports block-based shared storage such as Amazon EBS, Rackspace Cloud Block Storage, and EMC ScaleIO, as well as local storage (currently Experimental using our ZFS storage backend) so you can choose any of :ref:`the available storage backends <storage-backends>` that best suit your application.

.. XXX add link to choosing the best storage for your application marketing page (yet to be published)

.. _flocker-containers-architecture:

.. image:: images/flocker-architecture.svg
   :alt: Flocker architecture with shared storage backend.
         The Flocker Control Service and containers hosts can run on a VM or bare metal servers.
		 The Flocker Agent running on each host speaks to the shared storage backend to create and moutn volumes to individual containers.

.. _docker-plugin:

The Flocker Plugin for Docker
=============================

The Flocker plugin for Docker allows Flocker to manage your data volumes while using other tools such as Docker, Docker Swarm, or Mesos to manage your containers.
The Flocker plugin for Docker is a `Docker volumes plugin`_, connecting Docker on a host directly to Flocker, where Flocker agents will be running on the same host and hooked up to the Flocker control service.

.. XXX FLOC 3156 will add an architecture diagram to this document.

In contrast to the normal :ref:`Flocker container-centric architecture <flocker-containers-architecture>`, when using the Flocker plugin for Docker the Flocker volume manager (control service + dataset agents) is **being controlled by Docker**, rather than the Flocker container manager controlling Docker.
This allows for easier integration with other Docker ecosystem tools.

Also, please note that :ref:`Docker Swarm <labs-swarm>` and Flocker must be configured on the **same set of nodes**.

As a user of Docker, it means you can use Flocker directly via:

* The ``docker run -v name:path --volume-driver=flocker`` syntax.
* The ``VolumeDriver`` parameter on ``/containers/create`` in the Docker Remote API (set it to ``flocker``).

For more information, see the :ref:`using-docker-plugin` documentation, and the `Docker documentation on volume plugins`_.

The Flocker plugin for Docker depends on Docker 1.8 or later.

.. note::
    Note that you should either use the Flocker plugin for Docker to associate containers with volumes (the integration architecture described above), or you should use the :ref:`Flocker containers API <api>` and :ref:`flocker-deploy CLI <cli>`, but not both.

    They are distinct architectures.
    The integration approach allows Docker to control Flocker via the Flocker Dataset API.
    This allows Flocker to be used in conjunction with other ecosystem tools like :ref:`Docker Swarm <labs-swarm>` and :ref:`Docker Compose <labs-compose>`.

.. _`Docker volumes plugin`: https://github.com/docker/docker/blob/master/docs/extend/plugins_volume.md
.. _`Docker documentation on volume plugins`: `Docker volumes plugin`_

How It Works
------------

The Flocker plugin for Docker enables you to run containers with named volumes without worrying which server your data is on.

The plugin will create or move the volumes in place as necessary.

The Flocker plugin for Docker operates on the ``name`` passed to Docker in the ``docker run`` command and associates it with a Flocker dataset with the same name (i.e. with metadata ``name=foo``).

There are three main cases which the plugin handles:

* If the volume does not exist at all on the Flocker cluster, it is created on the host which requested it.
* If the volume exists on a different host, it is moved in-place before the container is started.
* If the volume exists on the current host, the container is started straight away.

Multiple containers can use the same Flocker volume (by referencing the same volume name, or by using Docker's ``--volumes-from``) so long as they are running on the same host.

Demo
----

This demo shows both the Flocker plugin for Docker in conjunction with the :ref:`Volumes CLI <labs-volumes-cli>` and :ref:`Volumes GUI <labs-volumes-gui>`.

.. raw:: html

   <iframe width="100%" height="450" src="https://www.youtube.com/embed/OhWxJ_hOPx8?rel=0&amp;showinfo=0" frameborder="0" allowfullscreen style="margin-top:1em;"></iframe>

Also check out the `DockerCon Plugin Demos <https://plugins-demo-2015.github.io/>`_ site to see a joint project between ClusterHQ and Weaveworks.
This is the "ultimate integration demo", a pre-built demo environment that includes Flocker, Weave, Swarm, Compose, and Docker, all working together in harmony.

Flocker also has planned integrations with major orchestration tools such as Docker Swarm, Kubernetes and Apache Mesos.
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

.. _storage-backends:

List of Storage Backends
========================

The following backends can be used with Flocker:

* AWS EBS
* Rackspace Cloud Block Storage
* Anything that supports the OpenStack Cinder API
* EMC ScaleIO
* EMC XtremIO
* VMware
* NetApp OnTap
* Hedvig
* ConvergeIO
* Saratoga Speed
* Local storage using our ZFS driver (currently Experimental)

Configuration details for each of the backends can be found in the :ref:`Configuring the Nodes and Storage Backends<agent-yml>` topic.

.. XXX FLOC 3144 - add a link here to the instructions on how to create your own backend driver

.. _get-started:

Get Started with Flocker
========================

Before you begin to install Flocker, there are a couple of ways in which you can try out Flocker without having to go through the full installation steps:

Flocker in a Live Hosted Environment
------------------------------------

You can take Flocker for a spin using a free, live hosted environment. 
No installation is required, and it’s great for getting a hands-on introduction to what Flocker is all about.

* The live demo environment is hosted by ClusterHQ.
* The demo environment will include a fully-installed and configured 2-node Flocker cluster and CLI.
* You will have root access to this environment, so you can test Flocker however you want.
* Follow a step-by-step tutorial.
* To give you time to play, you’ll have access to the environment for 3 hours.

For more information, see the `Try Flocker`_ page.

.. _vagrant-install:

Flocker Installed Locally Using Vagrant
---------------------------------------

If you don’t want to use real servers, you can set up a cluster locally on virtual machines using our Vagrant image.

Our MongoDB tutorial uses both VirtualBox and Vagrant to install Flocker and Docker, and walks you through an end-to-end example of using Flocker to create an application.

For more information, see the :ref:`MongoDB tutorial <tutorial-mongo>`.

.. _Try Flocker: https://clusterhq.com/flocker/try-flocker/live/
