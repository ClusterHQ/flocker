Flocker Volume Manager
----------------------

The Flocker Volume Manager (``FVM``) provides snapshotting and replication of Flocker volumes.
It has the ability to push volumes to remote nodes, track changes to those volumes, and roll them back to earlier states.

Although initially built on top of ZFS, FVM should eventually be capable of being backed on a number of filesystems.
As such a generic data model is required.


.. _volume-manager-data-model:

Data Model
==========

Motivation:

* ZFS has some peculiarities in its model when it comes to clones, e.g. promoting a clone moves snapshots from original dataset to the clone.
* Having clones be top-level constructs on the same level as originating dataset is a problem, since they are closely tied to each other both in terms of usage and in administrative “cleaning up old data” way.
* We don’t want to be too tied to the ZFS model (or terminology!) in case we want to switch to Btrfs or some other system.
  Especially given conflicting terminology - Btrfs “snapshots” are the same as ZFS “clones”.
* When it comes to replication, it is probably useful to differentiate between “data which is a copy of what the remote host has” and “local version”, in particular when divergence is a potential issue (e.g. can be caused by erroneous failover).
  In git you have “origin/branchname” vs. the local “branchname”, for example.

We are therefore going to be using the following model for CLI examples below:

* A “**volume**” is a tree of “**branches**”.
* A “**tag**” is a named read-only pointer to the contents of a branch at a given point in time; it is attached to the volume, and is not mounted on the filesystem.
* Given volume called “mydata”, “mydata/trunk” is (by convention) is the main branch from which other branches originate, “mydata/branchname” is some other branch, and “mytag@mydata” is a tag.
* Branches’ full name includes the Flocker instance they came from (by default let’s say using its hostname), e.g. “somehost/myvolume/trunk”. “dataset/branch” is shorthand for the current host, e.g. “thecurrenthost.example.com/dataset/branch”. In a replication scenario we could have “remote.example.com/datavolume/trunk” and “thecurrenthost.example.com/datavolume/trunk” (aka “datavolume/trunk”) as a branch off of that.
* Local branches are mounted on the filesystem, and then exposed to Docker, e.g. “myvolume/trunk” is exported via a docker container called “``flocker:myvolume/trunk``” (“``flocker:``” prefix is not a Docker feature, just a proposed convention for naming our containers).
* Remote branches are not mounted, but a local branch can be created off of them and then that is auto-mounted.


Implementation Notes - ZFS
^^^^^^^^^^^^^^^^^^^^^^^^^^

The names of volumes, branches and tags do not map directly onto the ZFS naming system.

Each Flocker instance has a UUID, with a matching (unique across a Flocker cluster) human readable name, typically the hostname.
We can imagine having two Flocker instances on same machine (with different pools) for testing, so don't want to require hostname.
This is the first part of the <Flocker instance UUID>/<volume UUID>/<branch name> triplet of branch names - in human-exposed CLI we probably want to use human names though, not UUIDs.
Branches are known to be local if branch’s specified Flocker instance matches the UUID of the Flocker process that is managing it.

Volumes have UUIDs, and a matching (cluster unique?) human readable name.
Tags are indicated by having a snapshot with a user attributes indicating it is a tag, the tag name and the volume name.
However, not all ZFS snapshots will be exposed as tags.
E.g. the fact that a snapshot is necessary for cloning (and therefore branch creation) is an implementation detail; sometimes you want to branch off a tag, but if you want to branch off of latest version the fact that a snapshot is created needn't be exposed.

A remote branch exists if there is a non-tag ZFS snapshot naming it, i.e. the snapshot has a user attribute indicating which branch it’s on (e.g. “``thathost/somevolume/abranch``”).

In either case the ZFS-level snapshot name is the Flocker instance UUID + the timestamp when it was generated.

A local branch exists due to local existence ZFS dataset, one of:

1. A root dataset (“trunk”), if this is the primary host (whatever that means).
2. A clone of a remote branch snapshot.
3. A clone of a local branch snapshot.

The branch name is stored as a user attribute on the ZFS dataset.
Dataset names can be the branch human readable names, since only one Flocker instance will ever be setting them.

In cases where we can’t use attributes the data will be in a local database of some sort.
E.g. ZFS properties are inherited automatically (not the behavior we want), which might lead to some corrupt state in crashes if the low-level APIs don’t allow bypassing this…


Implementation Notes - Btrfs
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Btrfs does not have a concept of clones - it just has snapshots, and they are mounted and writable.
As such the proposed model should also work with Btrfs.
Btrfs appears to lack promotion, but that can be emulated via renames.
It’s not clear if Btrfs has the “can’t delete parent if it has children” restriction, though it may just keep around extra disk storage in that case.
