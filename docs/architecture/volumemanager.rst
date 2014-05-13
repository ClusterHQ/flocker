Volume Manager Flocker Service
------------------------------

Flocker manages what Docker calls "volumes": self-contained filesystems storing application data for a specific application data.
For example, MySQL's ``/var/lib/mysql`` folder which contains the database files would be a good candidate for a volume.
Flocker is a daemon that runs on a machine; it can be controlled via an API and a command-line program that talks to the API.


Entities
========

A **pool** is used to store datasets.

A **volume** is a set of data for use with a specific application.
A dataset has a name identifying it.
For example, "example.com website MySQL data".
A dataset may also have a parent (see cloning below).
It can be mounted within the global Linux filesystem, or unmounted.
Volumes can store arbitrary user metadata.

A Flocker **snapshot** is a static pointer at the contents of a volume at a particular time.
Snapshots store the host they were created on and the time they were created.
Snapshots have a name.
Snapshots can store arbitrary user metadata.


Minimal API
===========

Probably worth modeling on Docker; accessible either over HTTPS or over unix socket.

* List Volumes
* Create Volume
* Destroy Volume
* Mount Volume
* Unmount Volume
* Rollback to Snapshot

For a particular volume, one can also operate on snapshots:

* List Snapshots
* Create Snapshot
* Destroy Snapshot
* Clone: create new volume from a snapshot.


Extended API
============

These are harder - have to deal with divergent histories, security, and networking efficiency.
They should therefore perhaps be implemented a second phase.
On the other hand they are where our system starts being more than just thin wrapper around ZFS.

* Pull Snapshot: Allows one flocker daemon to get a copy of a snapshot from a different flocker daemon.
* Push Snapshot: Allows one flocker daemon to send a copy of a snapshot to a different flocker daemon.

Maybe nice to have:

* Import: Create new volume from a tarball.
* Export: Dump a volume to a tarball.


Setup
=====

The Flocker daemon needs to be configured with a pool: either a file, a partition, or the name of an existing pre-configured ZFS pool.


Backend
=======

We should try not to hard-code too much ZFSism, as we may add (or have contributed) btrfs support.
