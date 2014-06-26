Volume Manager
==============

Flocker comes with a volume manager, a tool to manage volumes that can be attached to Docker containers.
Of particular note is the ability to push volumes to different machines.

Theory of Operation
*******************

Each volume is a ZFS dataset.
Volumes are created with three parameters:

* The UUID of the volume manager that owns the volume.
  The creating volume manager's UUID (see below) is used to supply a value for this parameter.
* The logical name; this must be the same as the name of the container it will be mounted in.
  For example, for a container named ``"myapp-mongodb"`` a volume called ``"myapp-mongodb"`` will be created.
* A mount path, indicating where within a container the volume will be mounted.
  For example, for a Mongo server this would be ``"/var/lib/mongodb"`` since that is where Mongo stores its data.

Creating a volume will automatically create a container with a ``"-data"`` suffix that mounts the volume in the appropriate location.
Since Flocker adds a ``"flocker-"`` prefix to containers it creates, this prefix will also be added to the data container.
For example, if you create a volume called ``"myapp-mongodb"`` with mountpoint ``"/var/lib/mongodb"`` then a container called ``"flocker-myapp-mongodb-data"`` will be created that has the volume mounted at that path.

You can then use this volume manually using ``--volumes-from``::

    $ docker run --volumes-from flocker-myapp-mongodb-data --name mongodb openshift/centos-mongodb

Even easier, geard and therefore the Flocker orchestration system will automatically mount volumes from ``"flocker-myapp-mongodb-data"`` if you create a unit called ``"flocker-myapp-mongodb"``.


Volume Ownership and Push
^^^^^^^^^^^^^^^^^^^^^^^^^

Each volume is owned by a volume manager and only that volume manager can write to it; the UUID of the owner volume manager is encoded in the volume definition.
To begin with a volume is owned by the volume manager that created it.
A volume manager can push volumes it owns to another machine, in which case that volume manager will have a copy of the data.
However, the copy on that remote volume manager is not owned by that volume manager and it will therefore not be able to write to it.

Push is currently done over SSH.


Configuration
*************

Each host in a Flocker cluster has a universally unique identifier (UUID) for its volume manager.
This allows differentiating between locally owned volumes and volumes that are stored locally but are owned by remote hosts.
By default the UUID is stored in ``/etc/flocker/volume.json``.

The volume manager stores volumes inside a ZFS pool called ``flocker``.


``flocker-volume``
******************

Currently the only way to control the volume manager is via the ``flocker-volume`` command-line tool.
At the moment it is only used for pushing volumes between machines, functionality that is not intended to be used by human beings.

