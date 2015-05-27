.. _clustering:

========================
Data-Oriented Clustering
========================

Minimal Downtime Volume Migration
=================================

Flocker's cluster management logic uses the volume manager (see :ref:`volume`) to efficiently move containers' data between nodes.

Consider a MongoDB application with a 20GB volume being moved from node A to node B.
The naive implementation would be:

#. Shut down MongoDB on node A.
#. :ref:`Push<volume-push>` all 20GB of data to node B with no database running.
#. :ref:`Hand off<volume-handoff>` ownership of the volume to node B, a quick operation.
#. Start MongoDB on node B.

This method would cause significant downtime.

Instead Flocker uses a superior two-phase push:

#. Push the full 20GB of data in the volume from node A to a node B.
   Meanwhile MongoDB continues to run on node A.
#. Shut down MongoDB on node A.
#. Push only the changes that were made to the volume since the last push happened.
   This will likely be orders of magnitude less than 20GB, depending on what database activity happened in the interim.
#. Hand off ownership of the volume to node B, a quick operation.
#. Start MongoDB on node B.

MongoDB is only unavailable during the time it takes to push the incremental changes from node A to node B.
