Baseline Flocker Service
------------------------

Ultimately Flocker may be a complete HybridCluster re-implementation.
Initially Flocker will just do one of the things that HybridCluster does.
By focusing on a very limited scope Flocker will do the thing that it does extremely well and be easier to build.

Regardless of which area of the HybridCluster feature-set Flocker initially targets many pieces of its basic architecture will be the same.
This document covers some of those pieces.

Operating System
================

Flocker is a suite of software that runs on top of an existing operating system.
The operating system may be running directly on hardware (“bare metal”) or in a virtualized environment.
Throughout this documentation this operating system is referred to as the “base system”.

Flocker manages one guest operating system (presently limited to a Linux distribution) using a “container” technology (chroot, LXC, Docker, etc).
Throughout this documentation this operating system is referred to as the “user system”.
All persistent state associated with the user system is the single filesystem associated with it.
This is referred to as the “user filesystem”.

Flocker depends on many services from the base system but there are a few in particular that it depends on to a much greater degree.

  * It depends on ZFS to be able to cheaply snapshot, replicate, and roll-back the user filesystem.
  * It depends on the container technology to isolate the base system and the user system from each other.
  * It depends on the ability to get timely, cheap notification that a change has been made to the user filesystem.


Hosts
=====

Flocker requires one or more hosts running the base system.
The number of hosts and the benefit of having more or fewer depends on the particular service Flocker implements.


Configuration
=============

Flocker requires a small amount of configuration, mostly likely externally supplied (for example, by the installer).

  * credentials for administrator access
  * the internet addresses of the master and slave hosts
  * credentials used to allow the master and slave hosts to securely communicate with each other

This information is kept in simple configuration file (for example, a a ``.ini``\ -style file) on the base system.
The Flocker service is responsible for reading this configuration *and* for writing modifications to it
(more explicitly, neither users nor system administrators nor third-party software is allowed to read or write configuration directly).
Limiting direct access to the configuration simplifies the interface to Flocker and removes the need for certain kinds of configuration correctness checks.


User System
===========

The user filesystem consists of a complete (user-space) operating system installation.
Flocker is agnostic to the particular distribution of Linux installed on the user filesystem.
The user filesystem is used to boot the user system using LXC (via Docker ???).
Flocker is responsible for managing the lifetime of the user system.
This primarily consists of starting the system's init process on the master host and stopping it if the master host is ever demoted to a slave.
Flocker is roughly as concerned with the particulars of the ``init`` process as is the Linux kernel (that is, not very).
If the user system is a minimal PostgreSQL server with no other user-space services then the ``init`` process may simple be one that boots the PostgreSQL server.
The details of how to boot the user system may well be left up to Docker.

The specific storage strategy for the user filesystem may depend on the deployment environment.
The ideal strategy is to have a ZFS storage pool which directly contains all of the host's physical block devices (ie, HDDs or SSDs).
Using this strategy the base system's root filesystem and the user filesystem exist as normal ZFS filesystems in the ZFS storage pool.
This *may* be difficult due to issues putting the base system's root filesystem onto a ZFS filesystem and limitations of various deployment environments.

A similar strategy might be to partition one of the host's block devices and put the base system on one part and give the rest to a ZFS storage pool.
This may also be difficult in practice due to limitations of various deployment environments.

A simpler strategy is to create a large file on the base system's filesystem and use this as storage for a ZFS storage pool.
This makes no unusual demands on the deployment environment.
It does force all user filesystem I/O through multiple block and VFS interfaces which likely leads to poor performance.


Filesystem Change Notification
==============================

Flocker works best if the master knows exactly when the filesystem has changed.
It can react to that by snapshotting the filesystem and replicating the snapshot to the slave host.

A bad approximation of filesystem change notification is a time-based service.
This generates a change notification in a loop at a fixed interval.
For expediency this will probably be the initial change notification mechanism.

A later improved service may be based on ``blktrace`` or a custom kernel module.

Change notifications are consumed by the Flocker service and feed into the snapshotting system.


Filesystem Snapshotting
=======================

The user system uses ZFS as its filesystem to allow the fast, cheap creation of snapshots.
User data on the user filesystem is not guaranteed to be in a consistent state in each snapshot.
However, the inconsistencies are the same as can be expected from a system crash (eg due to power failure).
Many applications (not MySQL with MyISAM tables) can be expected to be robust against this circumstance already.

Snapshots are taken when there is reason to believe there have been changes to user data.
They are taken frequently to minimize the chance that any particular change will be lost.

Snapshots are fast and cheap but they are not free.
As new snapshots are created it eventually becomes necessary to destroy some older snapshots.
Decisions about which snapshots to destroy need to take into considerations of the replication system described below.
There may also be security considerations which call for extra snapshots to be retained
(for example, if the master host is taken over and the filesystem changed undesirable, it may be beneficial for the slave host to still have some older snapshots taken prior to the breakin).


Snapshot Replication
====================

For failover to the slave host to be possible, the slave host must have a copy of the user filesystem.
The slave host is continuously provided with an up-to-date copy of the filesystem by the master host.
This is accomplished by repeatedly copying snapshots from the master host to the slave host.

This is done using two features of ZFS:

  * the feature allowing the changes between an earlier and a later snapshot to be extracted as a stream of bytes (the “replication stream”)
  * the feature allowing the replication stream to be loaded into a different system to recreate the later snapshot

The replication system consumes events from the snapshotting system.
Any time a new snapshot is created on the master host it is replicated to the slave host as quickly as possible.

This feature depends on the loading system (the slave host in this case) already having the earlier of the two snapshots in its system.
This limitation requires the master host and the slave host to communicate so that a usable earlier snapshot can be selected.
The best snapshot to select is the newest snapshot on the slave host (an older snapshot may require sending redundant data).
Therefore the master host tries hard to keep a copy of that snapshot.

Failover recovery may involve recovering from divergence in the user filesystem.
Because changes to the user filesystem are quickly snapshotted, user filesystem divergence quickly leads to snapshot divergence.
Snapshot divergence prevents further snapshot replication from taking place.
Resolving this condition involves getting rid of some snapshots.
Depending on the extent of the divergence this step may require manual intervention from an administrator.
For sufficiently small divergences (amounting to only a handful of changes) the system may automatically resolve the divergence in favor of the newer version of the user filesystem.
Any time this happens the losing version of the user filesystem will have its unique data saved.
This may be referred to as “stashing”.


Network Communication
=====================

For the master host to know which snapshots need to be replicated to the slave host, it needs to know which snapshots the slave host has.
It also needs this information to decide which snapshots to use as the start of the replication stream.

For failover to be accomplished, either the master host or the slave host or both need to determine that the master host has become incapable of providing service.
After a failover has taken place, it is also necessary for the old master to learn that it has become the new slave.

The mechanism for exposing fast failover to users is to publish address records pointing at both the master and slave hosts in DNS.
Users who select the master host's address from DNS get direct access to user system network services.
Users who select the slave host's address from DNS have all of their traffic proxied to the master host.
Responsibility for configuring and hosting these DNS records is beyond the scope of Flocker.
When one of the hosts has failed and well-behaved client software selects that host's address from DNS, the client software will try again with the other address.

The master host needs to expose the user system to the network as if the user system were a “normal”, non-Flocker system (or as close to this as possible).
The slave host needs to perform the proxying described above.

Both the master and the slave hosts need to expose information about their internal state for debugging and general informational purposes.


Failover
========

When the master host becomes incapable of providing service (eg, because it loses power, because it suffers a hardware failure, because it loses network connectivity, etc) the user system is “failed over” to the slave host.
The slave host becomes the new master host at this point.

Flocker initially takes a very simplistic approach to determining which the master host has become incapable of providing service.
During normal operation the master host and the slave host exchange messages frequently.
In addition to these normal, data-carrying, operational messages there may also be a “status” protocol.
This protocol exists to to ensure that each host always knows the operational status of the other.
The operational status comprises a number of facts:

  1. The capability to exchange simple network traffic with the other Flocker host.
  2. Persistent storage availability (the disk is not full, the disk has not failed, reads on the disk are serviced in a reasonable window).

This list may be expanded with other useful metrics for “capable of providing service” as they are determined.
When one of the hosts fails the other will learn of this in one of two ways:

  1. explicitly via the content of a “status” protocol message (“my disk has failed”)
  2. implicitly via the lack of any messages (because the entire host has crashed, its network provider has suffered an outage, etc)

This is the trigger for considering the other host to have failed.
