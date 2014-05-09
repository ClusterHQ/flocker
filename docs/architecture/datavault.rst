Flocker “DataVault” Service
---------------------------

The Flocker DataVault service provides point-in-time snapshots of the user filesystem.
It allows the user to roll the system back to any of these snapshots.


Hosts
=====

Flocker provides additional functionality to a single Linux host.
Installs of Flocker on multiple hosts are unrelated to each other.


Filesystem Snapshotting
=======================

Flocker keeps as many snapshots of the user filesystem as possible.
The utility of the Flocker service is the ability to roll the whole system back to an earlier state.
The more choices the service can offer about which earlier state the more useful the service is.


Snapshot Destruction
^^^^^^^^^^^^^^^^^^^^

Small variations in the exact point in time are more likely to be relevant for more recent system states.
That is, a one hour difference in system state is more likely to be important for the system state sometime yesterday than it is sometime last year.
Flocker destroys snapshots as necessary in a way which prefers to keep more recent snapshots than older snapshots.
It does this without completely destroying all older snapshots so that the option to roll the system back to a state from a month or a year ago is still available.
Or perhaps it uses some `more sophisticated technique <http://users.soe.ucsc.edu/%7Esbrandt/290S/efs.pdf>`_ to provide the desired user experience (to be decided).


User Experience
===============

A rollback must be initiated by a user system administrator (from Flocker's perspective, a user).
The Flocker service presents a user interface which exposes information about what snapshots are available.
Initially this information is probably limited to timestamps indicating when the snapshots were taken.
A more sophisticated DataVault service might offer more information.
For example, it might show what changes were made between two snapshots or allow browsing of the filesystem as it existed in a particular snapshot.

A rollback necessarily discards changes to the user filesystem which happened after the snapshot which is the target of the rollback.
Divergence in the snapshots for a particular filesystem is not supported by ZFS.
Flocker accounts for this by saving (or “stashing”) all affected filesystem changes outside of ZFS proper before performing the rollback.
This avoids destroying the data while still conforming to ZFS's limitations.
At some point it will be necessary to present the user with an interface for viewing and discarding this stashed data.

The specific implementation strategy for stashing this data has not been selected.
One approach is to use ``zfs send`` to generate the replication stream for the affected snapshots and save this data.
Another approach involves creating a ZFS clone of the newest snapshot and then promoting it to be the parent
(this may prove more flexible since it leaves the data accessible as a ZFS filesystem).
