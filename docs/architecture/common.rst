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

This information is kept in a simple configuration file (for example, an ``.ini``\ -style file) on the base system.
The Flocker service is responsible for reading this configuration *and* for writing modifications to it
(more explicitly, neither users nor system administrators nor third-party software is allowed to read or write configuration directly).
Limiting direct access to the configuration simplifies the interface to Flocker and removes the need for certain kinds of configuration correctness checks.


User System
===========

The user filesystem consists of a complete (user-space) operating system installation.
Flocker is agnostic to the particular distribution of Linux installed on the user filesystem.
The user filesystem is used to boot the user system using LXC (probably using Docker - to be decided).
Flocker is responsible for managing the lifetime of the user system.
This primarily consists of starting the system's init process on the master host and stopping it if the master host is ever demoted to a slave.
Flocker is roughly as concerned with the particulars of the ``init`` process as is the Linux kernel (that is, not very).
If the user system is a minimal PostgreSQL server with no other user-space services then the ``init`` process may be one that boots the PostgreSQL server.
The details of how to boot the user system may well be left up to Docker.

The specific storage strategy for the user filesystem may depend on the deployment environment.
The ideal strategy is to have a ZFS storage pool which directly contains all of the host's physical block devices (ie, HDDs or SSDs).
Using this strategy the base system's root filesystem and the user filesystem exist as normal ZFS filesystems in the ZFS storage pool.
This *may* be difficult due to issues putting the base system's root filesystem onto a ZFS filesystem and limitations of various deployment environments.

A similar strategy might be to partition one of the host's block devices and put the base system on one part and give the rest to a ZFS storage pool.
This may also be difficult in practice due to limitations of various deployment environments.

A simpler strategy is to create a large file on the base system's filesystem and use this as storage for a ZFS storage pool.
This makes no unusual demands on the deployment environment.
It does force all user filesystem I/O through multiple block and VFS interfaces which likely leads to poor performance
(performance issues might be mitigated somewhat using ZFS's built-in compression features).


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
A future improvement which may be possible is to expose hooks to the user system to allow it to make itself consistent prior to the creation of snapshots.

Snapshots are taken when there is reason to believe there have been changes to user data.
They are taken frequently to minimize the chance that any particular change will be lost.


Snapshot Destruction
^^^^^^^^^^^^^^^^^^^^

Snapshots are fast and cheap but they are not free.
The unique data referenced by a particular snapshot must be stored on disk as long as that snapshot exists.
If snapshots are never destroyed and the user filesystem continues to change then eventually storage space will be exhausted.
Additionally, the user interface challenges involved with presenting hundreds or thousands or tens of thousands of snapshots are substantial.
Therefore, as new snapshots are created it eventually becomes necessary to destroy some older snapshots.
Service-specific considerations will also influence decisions about which snapshots to destroy.
See the service-specific documentation for details.


User System Roll-back
=====================

The user filesystem can be returned to any earlier state for which a snapshot exists.
Combined with a restart of the processes in the user system this is a “rollback”.
(Details of how a restart is performed depends on whether we decode to use Docker and what hooks we want to expose to the user system.)
