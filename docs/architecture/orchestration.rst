Flocker “Orchestration” Service
---------------------------

The Flocker Orchestration service provides provisioning functionality for Docker containers across a number of hosts.
It also provides a replicated storage area within each container for mutable data.
Containers can be migrated between hosts in the cluster.


Hosts
=====

Flocker provides multi-tenant container hosting to multiple Linux hosts.
Normal operation requires at least 2 hosts within the cluster.
Some functionality can still be provided with only a single host.
Each container on the cluster has a single *master* host.
The container is running on that host.
Changes to the container's storage area are replicated to one or more *slave* host.
The slave host has an image of the Docker container and receives the snapshotted changes to the container's storage area.


Filesystem Snapshotting
=======================

See :ref:`flocker-failover`.

User Experience
===============

A roll back must be initiated by a user system administrator (from Flocker's perspective, a user).
The Flocker service presents a user interface which exposes information about what snapshots are available.
Initially this information is probably limited to timestamps indicating when the snapshots were taken.
A more sophisticated DataVault service might offer more information.
For example, it might show what changes were made between two snapshots or allow browsing of the filesystem as it existed in a particular snapshot.
