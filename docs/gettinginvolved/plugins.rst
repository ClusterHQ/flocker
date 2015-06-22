.. _dataset-backend-plugins:

=======================
Dataset Backend Plugins
=======================

Flocker supports pluggable storage backends; this document will teach you how to implement block device backends.
If you have any questions not addressed by this document please get in touch with us, e.g. Stopping by the ``#clusterhq`` channel on ``irc.freenode.net`` or filing an issue at https://github.com/ClusterHQ/flocker.

Block device backends
=====================

Flocker implements generic logic for network-based block device storage.
Examples of such storage include :ref:`Amazon EBS<aws-dataset-backend>` and :ref:`EMC ScaleIO and XtremIO<emc-dataset-backend>`.
If you wish to support a block device that is not supported by Flocker or an existing plugin you can implement this support yourself.

In order to do so you must write a Python 2.7 library providing a class implementing the `flocker.node.agents.blockdevice.IBlockDeviceAPI <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/blockdevice.py>`_ interface.
Flocker itself provides a `loopback <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/blockdevice.py>`_ implementation (for testing, lacking data movement), `OpenStack Cinder <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/cinder.py>`_ and `Amazon EBS <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/ebs.py>`_; these can serve as examples of implementation.

To test that your implementation is correct you can instantiate a generic test suite that makes sure your class correctly implements the interface:

.. code-block:: python

    from uuid import uuid4
    from flocker.node.agents.test.test_blockdevice import make_istatechange_tests

    def api_factory(test):
        # Return an instance of your IBlockDeviceAPI implementation class, given
        # a twisted.trial.unittest.TestCase instance.

    # Smallest volume to create in tests, e.g. 1GiB:
    MIN_ALLOCATION_SIZE = 1024 * 1024 * 1024

    # Minimal unit of volume allocation, e.g. 1MiB:
    MIN_ALLOCATION_UNIT = 1024 * 1024

    class YourStorageTests(make_istatechange_tests(
        api_factory, MIN_ALLOCATION_SIZE, MIN_ALLOCATION_UNIT,
        # Factory for valid but unknown volume id specific to your backend:
        lambda test: unicode(uuid4()))):
        """
        Tests for your storage.
        """

You can run these tests with ``trial`` test runner provided by `Twisted <https://twistedmatrix.com/trac/>`_, one of Flocker's dependencies:

.. prompt:: bash $

    trial yourstorage.test_yourstorage


Implementing storage plugins
============================

Once you've implemented your storage backend you'll want to allow Flocker users to utilize your package.
The basic implementation strategy is that your users install a Python package with your backend implementation on all Flocker nodes:

.. prompt:: bash $

    /opt/flocker/bin/pip install https://example.com/your/storageplugin-1.0.tar.gz

You can also provide RPMs or DEBs that have same effect of installing a new Python package.

Once your users have installed the package, they will write a :file`/etc/flocker/agent.yml` whose ``backend`` key in the ``dataset`` section is the importable name of the Python package you've installed.
All other sub-keys of the ``dataset`` section will be passed to a function you must implement (see below) and can be used to configure the resulting ``IBlockDeviceAPI`` instance.
Typical parameters are authentication information or server addresses; whatever is necessary to configure your class.

For example, if you installed a Python package importable ``mystorage_flocker_plugin``, and you require a username and password in order to log in to your storage system, you might tell your users to write a :file:`agent.yml` that looks like this:

.. code-block:: yaml

   version: 1
     control-service:
       hostname: "user.controlserver.example.com"
     dataset:
       backend: "mystorage_flocker_plugin"
       username: "username_for_mystorage"
       password: "abc123"

Your :file:`mystorage_flocker_plugin/__init__.py` module needs to have a ``FLOCKER_BACKEND`` attribute with a ``flocker.node.BackendDescription`` instance, which will include a reference to factory function that constructs a ``IBlockDeviceAPI`` instance.
The factory function will be called with whatever parameters the ``dataset`` section in :file:`agent.yml` is configured with; in the above example that would be ``username`` and ``password``.
Here's what the module might look like:

.. code-block:: python

    from flocker.node import BackendDescription, DeployerType
    from mystorage_flocker_plugin._backend import MyStorageAPI

    def api_factory(cluster_id, **kwargs):
        return MyStorageAPI(cluster_id=cluster_id, username=kwargs[u"username"],
                            password=kwargs[u"password"])

    FLOCKER_BACKEND = BackendDescription(
        name=u"mystorage_flocker_plugin", # name isn't actually used for 3rd party plugins
        needs_reactor=False, needs_cluster_id=True,
        api_factory=api_factory, deployer_type=DeployerType.block)

The ``cluster_id`` parameter is a Python ``uuid.UUID`` instance uniquely identifying the cluster, useful if you want to build a system that supports multiple Flocker clusters talking to a shared storage backend.
