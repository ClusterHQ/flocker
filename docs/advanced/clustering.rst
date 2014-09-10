========================
Data-Oriented Clustering
========================

Minimal Downtime Volume Migration
=================================

Flocker's cluster management logic builds on the functionality of the volume manager (see :doc:`./volume/index`) to provide efficient support for moving containers with data across nodes.

Consider a MongoDB application with a 20GB volume being moved from node A to node B.
The naive implementation of shutting down the database on node A, copying the data to node B and then starting the database back up on node B would cause quite a bit of downtime. Instead Flocker follows the following procedure:

#. Push the full 20GB of data in the volume from node A to a node B.
   While this is happening MongoDB continues to run on node A.
#. Shut down MongoDB on node A.
#. Push only the changes that were made to the volume since the last push happened.
   This will likely be orders of magnitude less 20GB, depending on what database activity happened in the interim.
#. Hand off ownership of the volume to node B, a quick operation.
#. Start MongoDB on node B.

MongoDB is only unavailable during the time it takes to push the incremental changes from node A to node B.
