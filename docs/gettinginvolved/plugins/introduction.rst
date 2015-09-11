.. _intro-build-flocker-driver:

=================================================
Introduction to building a Flocker storage driver
=================================================

Flocker supports pluggable storage backends. 
That means that any storage system that is able to present itself as a network-based block device can serve as the underlying storage for a Docker data volume managed by Flocker.

If you wish to use a storage device that is not supported by Flocker or an existing plugin you can implement this support yourself.
This document will teach you how to implement a block device backend for a storage system of your choosing.

Your storage driver will be a Python 2.7 library providing a class implementing the `flocker.node.agents.blockdevice.IBlockDeviceAPI <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/blockdevice.py>`_ interface.

Flocker implements generic logic for network-based block device storage already and these implementations can serve as an examples (e.g. `OpenStack Cinder <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/cinder.py>`_ and `Amazon EBS <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/ebs.py>`_).

This document will also provide detailed instructions for testing, certifying and publishing your driver.

If you have any questions not addressed by this document, please get in touch with us by stopping by the ``#clusterhq`` channel on ``irc.freenode.net`` or filing an issue at https://github.com/ClusterHQ/flocker.