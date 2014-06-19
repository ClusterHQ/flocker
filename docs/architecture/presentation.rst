===============
Flocker And You
===============

Motivation
==========

* Docker does multiple isolated, reproducable application environments on a single machine: "containers".
  * Application state can be stored on local disk in "volumes" attached to containers.
  * Containers can talk to each other and external world via specified ports.
* What happens if you have more than one machine?
  * Where do containers run?
  * How do you talk to the container you care about?
  * How do containers across multiple machines talk to each other?
  * How does application state work if you move containers around?

Flocker - Orchestration
=======================

* Flocker can run multiple containers on multiple machines
* Flocker offers a configuration language to specify what to run and where to run it.


Flocker - Routing
=================

* Container configuration includes externally visible TCP port numbers.
* Connect to any machine on a Flocker cluster and traffic is routed to the machine hosting the appropriate container (based on port).
* Your external domain (``www.example.com``) configured to point at all nodes in the Flocker cluster (``1.1.1.2``, ``1.168.1.3``)


Flocker - Cross-container Communication
=======================================

* Container configuration describes links (port numbers) which are required to other containers. E.g. your web application container needs to talk to your database.
* Connections to any linked port inside the source container are routed to the correct port inside the target container.


Flocker - Application State
===========================

* Flocker manages ZFS filesystems as Docker volumes.  It attaches them to your containers.
* Flocker provides tools for copying those volumes between machines.
* If an application container is moved from one machine to another, Flocker automatically moves the volume with it.


User Experience
===============

* Flocker provides a command-line interface for manually deploying or re-deploying containers across machines.
* The tool operates on two distinct pieces of configuration:
  * Application
  * Deployment
* Your sysadmin runs a command like ``flocker-cluster deploy application-config.yml deployment-config.yml`` on their laptop.


Application Configuration
=========================

 * Application configuration describes what you want to run in a container.
   * it identifies a Docker image
   * a volume mountpoint
   * other containers to link to
   * externally "routed" ports
 * This configuration is expected to be shared between development, staging, production, etc environments.
 * Flocker 0.1 may not support automatic re-deployment of application configuration changes


Deployment Configuration
========================

* Deployment configuration describes how you want your containers deployed.
  * which machines run which containers
* This configuration can vary between development, staging, production, etc environments
  * Developer might want to deploy all of the containers on their laptop
  * Production might put database on one machine, web server on another machine, etc
* Reacting to changes to this configuration is the primary focus of Flocker 0.1.


Overall Implementation Strategy
===============================

* Don't Panic.
* This is the 0.1 approach.
* Future approaches will be very different.


Overall Implementation Strategy
===============================

* All functionality is provided as short-lived, manually invoked processes.
* ``flocker-cluster deploy`` connects to each machine over SSH and runs ``flocker-node`` to make the necessary deployment changes.
* Machines might connect to each other over SSH to copy volume data to the necessary place.


flocker-node
============

* 
