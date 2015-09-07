.. _loopback-dataset-backend:

==============================================================
Loopback Block Device Backend Configuration (INTERNAL TESTING)
==============================================================

The Loopback backend uses node-local storage as storage for datasets.
It has no data movement functionality.
It serves primarily as a development and testing tool for the other block device backend implementations.
You may find it useful if you plan to work on Flocker itself.
This backend has no infrastructure requirements: it can run no matter where the Flocker dataset agents run.
The configuration item to use Loopback should look like:

.. code-block:: yaml

   "dataset":
      "backend": "loopback"
      "root_path": "/var/lib/flocker/loopback"

The ``root_path`` is a local path on each Flocker dataset agent node where dataset storage will reside.
