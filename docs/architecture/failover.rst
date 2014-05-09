Flocker Failover Service
------------------------

The Flocker failover service provides high-availability for the user system.
It does this with two (broadly scoped) techniques:

  1. It replicates the user filesystem to a slave host.
  2. It detects service interruption for the master host and automatically fails over to the slave host.


Hosts
=====

During normal operation Flocker requires two hosts running the base system.
The *master* host mounts the user filesystem read-write, runs the user system, exposes itself to the Internet, etc.
It also replicates the user filesystem to the *slave* host.
The slave host accepts updates of that filesystem and otherwise stands by until an incident interferes with the master host's ability to provide service.
Then the slave host is promoted to be the master host.
It starts the user system using the most up-to-date replica of the user filesystem that it has.
If the original master host returns to service it is demoted to be the slave host and the system continues just as it was before but with the host roles reversed.
If the user filesystem has diverged on the master and slave hosts then a heuristic may be applied to select the best version to continue.
This may result in the original master regaining the master role and the original slave being demoted back to a slave.

While the original master host is compromised Flocker will allow the user system to continue operating using only one host.
However, as long as only one host is online the replication and failover features of Flocker will not be operational.

Flocker is intentionally limited to at most a two host configuration
(though a future service built on Flocker may expand this).


Configuration
=============

The failover service has a couple of additional configuration requirements above and beyond those mentioned in the common document:

  * the internet addresses of the master and slave hosts
  * credentials used to allow the master and slave hosts to securely communicate with each other


Filesystem Snapshotting
=======================

The minimum feature-set of the failover service requires that the master keep a certain ZFS snapshot which it can use to construct a replication stream for later changes.
The particular snapshot that is required is the newest snapshot which has previously been replicated to the slave host.
(This may change if the `ZFS bookmark <https://www.illumos.org/issues/4369>`_ functionality becomes usable.)
However, there may be security considerations which call for extra snapshots to be retained.
For example, if the master host is compromised and undesirable changes made to the filesystem, recovery may be eased if the slave host still has some snapshots taken prior to the breakin.


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
