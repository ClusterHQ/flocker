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
