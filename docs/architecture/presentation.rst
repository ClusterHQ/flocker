flocker
=======

Flocker is a command line tool that lets you easily manage distributed Docker containers and their volumes. 
Even stateless apps depend on many stateful services (logging, queues, databases, etc) and currently running these services in Docker containers in production is nearly impossible. 
Flocker aims to solve this problem by providing an orchestration framework that addresses the problem of state. 
This document mainly describes the architecture and features that will be present in the 0.1 release.  
Areas for potential future development are discussed at the end.

This project is under active development and version 0.1 will be released soon under and Apache 2.0 license.  
Until you can start hacking on it with us, star this repo to stay up-to-date on what is happening, or submit an issue if you have a question or feature request prior to the initial release. 


Flocker is being developed by `ClusterHQ`_.  
ClusterHQ is a small team of engineers with experience running distributed systems and includes many of the core contributors to the Twisted Python project.

Table of Contents
=================

0. Motivation for building Flocker
1. Architecture
2. Overall implementation strategy
3. User experience
4. Example- running trac with PostgresSQL and Elasticsearch
5. Areas of potential future development

0. Motivation for building Flocker
===============================

* Docker does multiple isolated, reproducible application environments on a single machine: "containers".

  * Application state can be stored on local disk in "volumes" attached to containers.
  * Containers can talk to each other and external world via specified ports.
  
* What happens if you have more than one machine?

  * Where do containers run?
  * How do you talk to the container you care about?
  * How do containers across multiple machines talk to each other?
  * How does application state work if you move containers around?

1. Architecture
============

Flocker - Orchestration
-----------------------

* Flocker can run multiple containers on multiple machines.
* Flocker offers a configuration language to specify what to run and where to run it.


Flocker - Routing
-----------------

* Container configuration includes externally visible TCP port numbers.
* Connect to any machine on a Flocker cluster and traffic is routed to the machine hosting the appropriate container (based on port).
* Your external domain (``www.example.com``) configured to point at all nodes in the Flocker cluster (``1.1.1.2``, ``1.168.1.3``)


Flocker - Cross-container communication
---------------------------------------

* Container configuration describes links (port numbers) which are required to other containers. 
  E.g. your web application container needs to talk to your database.
* Connections to any linked port inside the source container are routed to the correct port inside the target container.


Flocker - Application state
---------------------------

* Flocker manages ZFS filesystems as Docker volumes.  It attaches them to your containers.
* Flocker provides tools for copying those volumes between machines.
* If an application container is moved from one machine to another, Flocker automatically moves the volume with it.



Application configuration
-------------------------

* Application configuration describes what you want to run in a container.

  * it identifies a Docker image
  * a volume mountpoint
  * other containers to link to
  * externally "routed" ports
   
* This configuration is expected to be shared between development, staging, production, etc environments.
* Flocker 0.1 may not support automatic re-deployment of application configuration changes.


Deployment configuration
------------------------

* Deployment configuration describes how you want your containers deployed.

  * which machines run which containers.
  
* This configuration can vary between development, staging, production, etc environments.

  * Developer might want to deploy all of the containers on their laptop.
  * Production might put database on one machine, web server on another machine, etc.
  
* Reacting to changes to this configuration is the primary focus of Flocker 0.1.


2. Overall implementation strategy
==================================

* Don't Panic.
* This is the 0.1 approach.
* All functionality is provided as short-lived, manually invoked processes.
* ``flocker-cluster deploy`` connects to each machine over SSH and runs ``flocker-node`` to make the necessary deployment changes.
* Machines might connect to each other over SSH to copy volume data to the necessary place.
* Future approaches will be very different.  
  Feedback welcome.

flocker-node
------------

* Installed and runs on machines participating in the Flocker cluster.
* Accepts the desired global configuration.
* Looks at local state - running containers, configured network proxies, etc.
* Makes changes to local state so that it complies with the desired global configuration.

  * Start or stop containers.
  * Push volume data to other machines.
  * Add or remove routing configuration.


Managing Containers
-------------------

* `Geard`_ is used to start, stop, and enumerate containers.
* Geard works by creating systemd units.
* Systemd units are a good way to provide admin tools for:

  * logging and state inspection.
  * starting/stopping (including at boot).
  * inter-unit dependency management.
  * lots of other stuff.
  
* Geard helps support the implementation of links.


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
	
  * Volumes can be "handed off" to another machine.  
    Machine A can hand off the volume to machine B.  
	Then machine B can modify the volume and machine A no longer can.
	
* Volumes are pushed and handed off so as to follow the containers they are associated with.

  * This happens automatically when ``flocker-cluster deploy`` runs with a new deployment configuration.


Managing routes
---------------

* Containers claim TCP port numbers with the application configuration that defines them.
* Connections to that TCP port on the machine that is running the container are proxied (NAT'd) into the container for whatever software is listening for them there.
* Connections to that TCP port on any other machine in the Flocker cluster are proxied (NAT'd!) to the machine that is running the container.
* Proxying is done using iptables.


Managing links
--------------

* Containers declare other containers they want to be able to talk to and on what port they expect to be able to do this.
* Geard is told to proxy connections to that port inside the container to localhost on the machine hosting that container.
* The routes code makes ensures the connection is then proxy to the machine hosting the target container.

3. User experience
==================

* Flocker provides a command-line interface for manually deploying or re-deploying containers across machines.
* The tool operates on two distinct pieces of configuration:

  * Application
  * Deployment
  
* Your sysadmin runs a command like ``flocker-cluster deploy application-config.yml deployment-config.yml`` on their laptop.


4. Example - running trac with Postgresql and Elasticsearch
===========================================================

* Alice wants to run trac using the postgresql backend and kibana for log analysis.
* trac needs to connect to postgresql and shovel logs over to kibana.
* trac and postgresql will run on one host (one cpu heavy container, one disk heavy container).
* elasticsearch and kibana will run on a second host (same deal).


Example - trac configuration
----------------------------

.. code-block::

  trac = {
      "image": "clusterhq/trac",
      "volume": "/opt/trac/env",
      "environment": {
          "ELASTICSEARCH_PORT": unicode(elasticsearch_port_number),
      },
      "routes": [https_port_number],
      "links": [
          ("pgsql-trac", pgsql_port_number),
          ("elasticsearch-trac", log_consumer_port_number),
      ],
  }


Example - postgresql configuration
----------------------------------

.. code-block::

   postgresql = {
       "image": "clusterhq/postgresql",
       "volume": "/var/run/postgresql",
       "routes": [pgsql_port_number],
       "links": [],
   }


Example - elasticsearch configuration
-------------------------------------

.. code-block::

   elasticsearch = {
       "image": "clusterhq/elasticsearch",
       "volume": "/var/run/elasticsearch",
       "routes": [elasticsearch_port_number],
       "links": [],
   }


Example - kibana configuration
------------------------------

.. code-block::

   kibana = {
       "image": "clusterhq/elasticsearch",
       "volume": "/var/run/elasticsearch",
       "environment": {
           "ELASTICSEARCH_RESOURCE": "http://localhost:%d" % (elasticsearch_port_number,),
       },
       "routes": [alternate_https_port],
       "links": [
           ("elasticsearch-trac", elasticsearch_port_number),
           ],
   }


Example - Application configuration
-----------------------------------

Aggregate all of the applications

.. code-block::

   application_config = {
       "trac": trac,
       "pgsql-trac": postgresql,
       "elasticsearch-trac": elasticsearch,
       "kibana-trac": kibana,
   }


Example - Deployment configuration
----------------------------------

Explicitly place containers for the applications

.. code-block::

   deployment_config = {
       "nodes": {
           "1.1.1.1": ["trac", "pgsql-trac"],
           "1.1.1.2": ["elasticsearch-trac", "kibana-trac"],
       },
   }


Example - User interaction
--------------------------

Imagine some yaml files containing the previously given application and deployment configuration objects.

.. code-block::

   $ flocker-cluster deploy application_config.yml deployment_config.yml
   Deployed `trac` to 1.1.1.1.
   Deployed `elasticsearch-trac` to 1.1.1.2.
   Deployed `pgsql-trac` to 1.1.1.1.
   Deployed `kibana-trac` to 1.1.1.2.
   $


Example - Alter deployment
--------------------------

It turns out trac is the most resource hungry container.
Give it an entire machine to itself.

The deployment configuration changes to:

.. code-block::

   deployment_config = {
       "nodes": {
           "1.1.1.1": ["trac"],
           "1.1.1.2": ["elasticsearch-trac", "kibana-trac", "pgsql-trac"],
       },
   }

.. code-block:: sh

   $ flocker-cluster deploy application_config.yml deployment_config.yml
   Re-deployed pgsql-trac from 1.1.1.1 to 1.1.1.2.
   $

Note that after pgsql-trac is moved it still has all of the same filesystem state as it had prior to the move.

5. Areas of potential future development
========================================
- Support for atomic updates.
- Scale-out for stateless containers.
- API to support managing Flocker volumes programmatically.
- Statically configured continuous replication and manual failover.
- No-downtime migrations between containers.
- Automatically configured continuous replication and failover.
- Multi-data center support.
- Automatically balance load across cluster.
- Roll-back a container to a snapshot.
- Let us know what else you'd like to see by submitting an issue :)

.. _Geard: https://github.com/openshift/geard
.. _ClusterHQ: https://clusterhq.com/

