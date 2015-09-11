.. _build-flocker-driver-prereq:

====================
Driver Prerequisites
====================

1. Your driver needs support to storing metadata for each volume on the storage backend.

2. The Driver needs a way to programmatically map a compute instance id to the input format expected by your storage backend for the attach operation. For example, if you have a 2 node compute+storage cluster on AWS, and your storage solution refers to the compute nodes as ``aws1`` and ``aws2``, your driver running on ``aws1`` would need be able to find out its compute instance name as ``aws1``, not ``i-1cf275d9`` which is the EC2 naming convention.

3. The driver needs a way to request default storage features like compression, dedup, IOPs, and SSD/HDD while creating a volume.

4. Optional - Please consider adding driver logs for debuggability.