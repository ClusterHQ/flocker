.. _build-flocker-driver-prereq:

===================================
Prerequisites For Building a Driver
===================================

When contributing a new Flocker storage driver, you will need to consider the following prerequisites:

* Your driver needs support for storing metadata for each volume on the storage backend.
* The driver needs a way to programmatically map a compute instance ID to the input format expected by your storage backend for the attach operation.
  For example, if you have a 2 node compute+storage cluster on AWS, and your storage solution refers to the compute nodes as ``aws1`` and ``aws2``, your driver running on ``aws1`` would need to be able to find out its compute instance name as ``aws1``, not ``i-1cf275d9`` (which is the EC2 naming convention).
* The driver needs a way to request default storage features like compression, data deduplication, IOPs, and SSD/HDD while creating a volume.
* Optional - Please consider adding driver logs for debugging.