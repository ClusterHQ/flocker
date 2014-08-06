============
Introduction
============

Motivation for building Flocker
===============================
Flocker lets you move your Docker containers and their data together between hosts.
This means that you can run your databases, queues and key-value stores in Docker and move them around as easily as the rest of your app.
Even stateless apps depend on many stateful services and currently running these services in Docker containers in production is nearly impossible.
Flocker aims to solve this problem by providing an orchestration framework that allows you to port both your stateful and stateless containers between environments.


* Docker does multiple isolated, reproducible application environments on a single machine: "containers".

  * Application state can be stored on local disk in "volumes" attached to containers.
  * Containers can talk to each other and external world via specified ports.

* But what happens if you have more than one machine?

  * Where do containers run?
  * How do you talk to the container you care about?
  * How do containers across multiple machines talk to each other?
  * How does application state work if you move containers around?

Architecture
============

Flocker - Orchestration
-----------------------

* Flocker can run multiple containers on multiple machines.
* Flocker offers a configuration language to specify what to run and where to run it.


Flocker - Routing
-----------------

* Container configuration includes externally visible TCP port numbers.
* Connect to any machine on a Flocker cluster and traffic is routed to the machine hosting the appropriate container (based on port).
* Your external domain (``www.example.com``) configured to point at all nodes in the Flocker cluster (``192.0.2.0``, ``192.0.2.1``)


Flocker - Application state
---------------------------

* Flocker manages ZFS filesystems as Docker volumes.  It attaches them to your containers.
* Flocker provides tools for copying those volumes between machines.
* If an application container is moved from one machine to another, Flocker automatically moves the volume with it.


Application configuration
-------------------------

* Application configuration describes what you want to run in a container.

  * it identifies a Docker image
  * an optional volume mountpoint
  * externally "routed" ports

* This configuration is expected to be shared between development, staging, production, etc environments.
* Flocker 0.1 does not support automatic re-deployment of application configuration changes.


Deployment configuration
------------------------

* Deployment configuration describes how you want your containers deployed.

  * which machines run which containers.

* This configuration can vary between development, staging, production, etc environments.

  * Developer might want to deploy all of the containers on their laptop.
  * Production might put database on one machine, web server on another machine, etc.

* Reacting to changes to this configuration is the primary focus of Flocker 0.1.


Initial implementation strategy
===============================

* This is the 0.1 approach.
* Future approaches will be very different; feedback is welcome.
* All functionality is provided as short-lived, manually invoked processes.
* ``flocker-deploy`` connects to each machine over SSH and runs ``flocker-reportstate`` to gather the cluster state.
* ``flocker-deploy`` then connects to each machine over SSH and runs ``flocker-changestate`` to make the necessary deployment changes.
* Machines might connect to each other over SSH to copy volume data to the necessary place.

flocker-changestate
-------------------

* This is installed on machines participating in the Flocker cluster.
* Accepts the desired global configuration and current global state.
* Also looks at local state - running containers, configured network proxies, etc.
* Makes changes to local state so that it complies with the desired global configuration.

  * Start or stop containers.
  * Push volume data to other machines.
  * Add or remove routing configuration.


Managing Containers
-------------------

* `Geard`_ is used to start, stop, and enumerate containers.
* Geard works by creating systemd units.
* Systemd units are a good way to provide admin tools for:

  * Logging and state inspection.
  * Starting/stopping (including at boot).
  * Inter-unit dependency management.


Managing volumes
----------------

* Volumes are ZFS filesystems.
* Volumes are attached to a Docker "data" container.
* Geard automatically associates the "data" container's volumes with the actual container.

  * Association is done based on container names by Geard.

* Data model
  * Volumes are owned by a specific machine.

  * Machine A can push a copy to machine B but machine A still owns the volume.
    Machine B may not modify its copy.

  * Volumes can be "handed off" to another machine, i.e. ownership is changed.
    Machine A can hand off the volume to machine B.
    Then machine B is now the owner and can modify the volume and machine A no longer can.

* Volumes are pushed and handed off so as to follow the containers they are associated with.

  * This happens automatically when ``flocker-deploy`` runs with a new deployment configuration.


Managing routes
---------------

* Containers claim TCP port numbers with the application configuration that defines them.
* Connections to that TCP port on the machine that is running the container are proxied (NAT'd) into the container for whatever software is listening for them there.
* Connections to that TCP port on any other machine in the Flocker cluster are proxied (NAT'd!) to the machine that is running the container.
* Proxying is done using iptables.


User experience
===============

* Flocker provides a command-line interface for manually deploying or re-deploying containers across machines.
* The tool operates on two distinct pieces of configuration:

  * Application
  * Deployment

* Your sysadmin runs a command like ``flocker-deploy deployment-config.yml application-config.yml`` on their laptop.

.. _Geard: https://github.com/openshift/geard

