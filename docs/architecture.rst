Operating System
================

Flocker is a suite of software that runs on top of an existing operating system.
The operating system may be running directly on hardware (¨bare metal¨) or in a virtualized environment.
Throughout this documentation this operating system is referred to as the ¨base system¨.

Flocker manages a guest operating system (presently limited to a Linux distribution) using a ¨container¨ technology (chroot, LXC, Docker, etc).
Throughout this documentation this operating system is referred to as the ¨user system¨.

Flocker depends on many services from the base system but there are a few in particularly that it depends on to a much greater degree.

  * It depends on ZFS to be able to cheaply snapshot, replicate, and roll-back the user system's filesystem.
  * It depends on the container technology to isolate the base system and the user system from each other.
  * It depends on the ability to get timely, cheap notification that a change has been made to the user system's filesystem.


Hosts
=====

Flocker requires two hosts.
The *master* host mounts the user system's filesystem, runs the user system, exposes itself to the Internet, etc.
It also replicates the user system's filesystem to the *slave* host.
The slave host accepts updates of that filesystem and otherwise stands by until an incident interferes with the master host's ability to provide service.
Then the slave host is promoted to be the master host.
It starts the user system using the most up-to-date replica of the user system's filesystem that it has.
If the original master host returns to service it is demoted to be the slave host.


Configuration
=============

Flocker requires a small amount of externally supplied configuration.

  * credentials for administrator access
  * the internet addresses of the master and slave hosts
  * credentials used to allow the master and slave hosts to securely communicate with each other

This information is kept in a ``.ini``\ -style file on the base system.
The Flocker service is responsible for reading this configuration *and* for writing modifications to it.


Filesystem Change Notification
==============================

Flocker works best if the master knows exactly when the filesystem has changed.
It can react to that by snapshotting the filesystem and replicating the snapshot to the slave host.

A bad approximation of filesystem change notification is a time-based service.
This generates a change notification in a loop at a fixed interval.

A later improved service may be based on ``blktrace`` or a custom kernel module.

Change notifications are consumed by the Flocker service and feed into the snapshotting system.

Filesystem Snapshotting
=======================

The user system uses ZFS as its filesystem to allow the fast, cheap creation of snapshots.
User data on the user system's filesystem is not guaranteed to be in a consistent state in each snapshot.
However, the inconsistencies are the same as can be expected from a system crash (eg due to power failure).
Many applications (not MySQL with MyISAM tables) can be expected to be robust against this circumstance already.

Snapshots are taken when there is reason to believe there have been changes to user data.
They are taken frequently to minimize the chance that any particular change will be lost.

Snapshots are fast and cheap but they are not free.
As new snapshots are created it eventually becomes necessary to destroy some older snapshots.
Decisions about which snapshots to destroy need to take into considerations of the replication system described below.


Snapshot Replication
====================

For failover to the slave host to be possible, the slave host must have a copy of the user system's filesystem.
The slave host is continuously provided with an up-to-date copy of the filesystem by the master host.
This is accomplished by repeatedly copying snapshots from the master host to the slave host.

This is done using two features of ZFS:

  * the feature allowing the changes between an earlier and a later snapshot to be extracted as a stream of bytes (the ¨replication stream¨)
  * the feature allowing the replication stream to be loaded into a different system to recreate the later snapshot

The replication system consumes events from the snapshotting system.
Any time a new snapshot is created on the master host it is replicated to the slave host as quickly as possible.

This feature depends on the loading system (the slave host in this case) already having the earlier of the two snapshots in its system.
This limitation requires the master host and the slave host to communicate so that a usable earlier snapshot can be selected.
The best snapshot to select is the newest snapshot on the slave host (an older snapshot may require sending redundant data).
Therefore the master host tries hard to keep a copy of that snapshot.


Network Communication
=====================

For the master host to know which snapshots need to be replicated to the slave host, it needs to know which snapshots the slave host has.
It also needs this information to decide which snapshots to use as the start of the replication stream.

For failover to be accomplished, either the master host or the slave host or both need to determine that the master host has become incapable of providing service.
After a failover has taken place, it is also necessary for the old master to learn that it has become the new slave.

The master host needs to expose the user system to the network as if the user system were a ¨normal¨, non-Flocker system (or as close to this as possible).

Both the master and the slave hosts need to expose information about their internal state for debugging and general informational purposes.
