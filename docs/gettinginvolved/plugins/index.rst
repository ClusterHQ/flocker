.. _contribute-flocker-driver:

==========================================
Contributing a New Flocker Storage Backend
==========================================

Flocker supports pluggable storage backends. 
That means that any storage system that is able to present itself as a network-based block device can serve as the underlying storage for a Docker data volume managed by Flocker.

If you wish to use a storage device that is not supported by Flocker or an existing plugin, you can implement this support yourself.
The documents listed in the contents below will show you how to implement a block device backend for a storage system of your choosing.

Your storage driver must be a Python 2.7 library providing a class implementing the `flocker.node.agents.blockdevice.IBlockDeviceAPI <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/blockdevice.py>`_ interface.

Flocker implements generic logic for network-based block device storage already, and these implementations can serve as an examples:

* `OpenStack Cinder <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/cinder.py>`_
* `Amazon EBS <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/ebs.py>`_

The following documents will also provide detailed instructions for testing, certifying, and publishing your driver.
You will also find instructions on how to enable your driver to support :ref:`storage-profiles`.

If you have any questions not addressed in this section, please get in touch with us either via the ``#clusterhq`` channel on ``irc.freenode.net``, or by filing a `GitHub issue <https://github.com/ClusterHQ/flocker/issues>`_.
More information about contacting ClusterHQ can be found in our :ref:`talk-to-us` section.

.. toctree::
   :maxdepth: 2

   prereqs
   building-driver
   faq
