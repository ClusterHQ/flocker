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

* Installed and runs on machines participating in the Flocker cluster.
* Accepts the desired global configuration
* Looks at local state - running containers, configured network proxies, etc
* Makes changes to local state so that it complies with the desired global configuration
  * Start or stop containers
  * Push volume data to other machines
  * Add or remove routing configuration


Managing Containers
===================

* Gear is used to start, stop, and enumerate containers.
* Gear works by creating systemd units.
* Systemd units are a good way to provide admin tools for:
  * logging and state inspection
  * starting/stopping (including at boot)
  * inter-unit dependency management
  * lots of other stuff
* Gear helps support the implementation of links


Managing Volumes
================

* Volumes are ZFS filesystems.
* Volumes are attached to a Docker "data" container.
* Gear automatically associates the "data" container's volumes with the actual container.
  * Association is done based on container names by Gear.
* Data model
  * Volumes are owned by a specific machine.
  * Machine A can push a copy to machine B but machine A still owns the volume.  Machine B may not modify its copy.
  * Volumes can be "handed off" to another machine.  Machine A can hand off the volume to machine B.  Then machine B can modify the volume and machine A no longer can.
* Volumes are pushed and handed off so as to follow the containers they are associated with.
  * This happens automatically when ``flocker-cluster deploy`` runs with a new deployment configuration.


Managing Routes
===============

* Containers claim TCP port numbers with the application configuration that defines them.
* Connections to that TCP port on the machine that is running the container are proxied (NAT'd) into the container for whatever software is listening for them there.
* Connections to that TCP port on any other machine in the Flocker cluster are proxied (NAT'd!) to the machine that is running the container.
* Proxying is done using iptables.


Managing Links
==============

* Containers declare other containers they want to be able to talk to and on what port they expect to be able to do this.
* Gear is told to proxy connections to that port inside the container to localhost on the machine hosting that container.
* The routes code makes ensures the connection is then proxy to the machine hosting the target container.

Example - Overview
==================

* Alice wants to run trac using the postgresql backend and kibana for log analysis.
* trac needs to connect to postgresql and shovel logs over to kibana
* trac and postgresql will run on one host (one cpu heavy container, one disk heavy container)
* elasticsearch and kibana will run on a second host (same deal)

Example - trac configuration
============================

Maybe something like

```
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
```

Example - postgresql configuration
==================================

Maybe something like

```
postgresql = {
    "image": "clusterhq/postgresql",
    "volume": "/var/run/postgresql",
    "routes": [pgsql_port_number],
    "links": [],
}
```

Example - elasticsearch configuration
=====================================

Maybe something like

```
elasticsearch = {
    "image": "clusterhq/elasticsearch",
    "volume": "/var/run/elasticsearch",
    "routes": [elasticsearch_port_number],
    "links": [],
}
```

Example - kibana configuration
==============================

Maybe something like

```
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
```

Example - Application Configuration
===================================

Aggregate all of the applications

```
application_config = {
    "trac": trac,
    "pgsql-trac": postgresql,
    "elasticsearch-trac": elasticsearch,
    "kibana-trac": kibana,
}
```

Example - Deployment Configuration
==================================

Explicitly place containers for the applications

```
deployment_config = {
    "nodes": {
        "1.1.1.1": ["trac", "pgsql-trac"],
        "1.1.1.2": ["elasticsearch-trac", "kibana-trac"],
    },
}
```

Example - User Interaction
==========================

Imagine some yaml files containing the previously given application and deployment configuration objects.

```
$ flocker-cluster deploy application_config.yml deployment_config.yml
Deployed `trac` to 1.1.1.1.
Deployed `elasticsearch-trac` to 1.1.1.2.
Deployed `pgsql-trac` to 1.1.1.1.
Deployed `kibana-trac` to 1.1.1.2.
$
```

Example - Alter Deployment
==========================

It turns out trac is the most resource hungry container.
Give it an entire machine to itself.

The deployment configuration changes to:

```
deployment_config = {
    "nodes": {
        "1.1.1.1": ["trac"],
        "1.1.1.2": ["elasticsearch-trac", "kibana-trac", "pgsql-trac"],
    },
}
```

```
$ flocker-cluster deploy application_config.yml deployment_config.yml
Re-deployed pgsql-trac from 1.1.1.1 to 1.1.1.2.
$
```

Note that after pgsql-trac is moved it still has all of the same filesystem state as it had prior to the move.
