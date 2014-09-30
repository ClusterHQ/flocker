Volume Manager
==============

Flocker comes with a volume manager, a tool to manage volumes that can be attached to Docker containers.
Of particular note is the ability to push volumes to different machines.


Configuration
^^^^^^^^^^^^^

Each host in a Flocker cluster has a universally unique identifier (UUID) for its volume manager.
By default the UUID is stored in ``/etc/flocker/volume.json``.

The volume manager stores volumes inside a ZFS pool called ``flocker``.


Volume Ownership
^^^^^^^^^^^^^^^^

Each volume is owned by a specific volume manager and only that volume manager can write to it.
To begin with a volume is owned by the volume manager that created it.

.. _volume-push:

A volume manager can *push* volumes it owns to another machine, copying the volume's data to a remote volume manager.
The copied volume on that remote volume manager will continue to be owned by the local volume manager, and therefore the remote volume manager will not be able to write to it.

.. _volume-handoff:

A volume manager can also *handoff* a volume to a remote volume manager, i.e. transfer ownership.
The remote volume manager becomes the owner of the volume and subsequently it is able to write to the volume.
The volume manager that did the handoff ceases to own the volume and subsequently is not allowed to write to the volume.

Volumes are mounted read-write by the manager which owns them.
They are mounted read-only by any other manager which has a copy.


Implementation Details
^^^^^^^^^^^^^^^^^^^^^^

Each volume is a ZFS dataset.
Volumes are created with three parameters:

* The UUID of the volume manager that owns the volume.
  The creating volume manager's UUID (see above) is used to supply a value for this parameter.
* The logical name; this must be the same as the name of the container it will be mounted in.
  For example, for a container named ``"myapp-mongodb"`` a volume called ``"myapp-mongodb"`` will be created.
* A mount path, indicating where within a container the volume will be mounted.
  For example, for a MongoDB server this would be ``"/var/lib/mongodb"`` since that is where MongoDB stores its data.

The ZFS dataset name is a combination of the UUID and the logical name, e.g. ``1234.myapp-mongodb``.


Docker Integration
******************

When starting a container with a volume configured, Flocker checks for the existence of the volume.
If it does not exist a new ZFS dataset is created.
Flocker mounts the volume into the container as a normal Docker volume.

Push and Handoff
****************

Push and handoffs are currently done over SSH between nodes, with ad hoc calls to the ``flocker-volume`` command-line tool.
In future releases this will be switched to a real protocol and later on to communication between long-running daemons rather than short-lived scripts.
(See `#154 <https://github.com/ClusterHQ/flocker/issues/154>`_\ .)

When a volume is pushed a ``zfs send`` is used to serialize its data for transmission to the remote machine, which does a ``zfs receive`` to decode the data and create or update the corresponding ZFS dataset.

If the sending node determines that it has a snapshot of the volume in common with the receiving node
(as determined using ``flocker-volume snapshot``)
then it will construct an incremental data stream based on that snapshot.
This can drastically reduce the amount of data that needs to be transferred between the two nodes.

Handoff involves renaming the ZFS dataset to change the owner UUID encoded in the dataset name.
For example, imagine two volume managers with UUIDs ``1234`` and ``5678`` and a dataset called ``mydata``.

========================================== ======================== ======================
Action                                     Volume Manager 1234      Volume Manager 5678
========================================== ======================== ======================
1. Create ``mydata`` on ``1234``           ``1234.mydata`` (owner)
2. Push ``mydata`` to ``5678``             ``1234.mydata`` (owner)  ``1234.mydata``
3. Handoff ``mydata`` to ``5678``          ``5678.mydata``          ``5678.mydata`` (owner)
========================================== ======================== ======================
