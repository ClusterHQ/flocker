.. _dataset-backend-plugins:

========================================
Contribute a new Flocker storage backend
========================================

Flocker supports pluggable storage backends; this document will teach you how to implement block device backends.
If you have any questions not addressed by this document please get in touch with us, e.g. Stopping by the ``#clusterhq`` channel on ``irc.freenode.net`` or filing an issue at https://github.com/ClusterHQ/flocker.

Block device backends
=====================

Flocker implements generic logic for network-based block device storage.
Example of such storage includes :ref:`Amazon EBS<aws-dataset-backend>`.
If you wish to support a block device that is not supported by Flocker or an existing plugin you can implement this support yourself.

In order to do so you must write a Python 2.7 library providing a class implementing the `flocker.node.agents.blockdevice.IBlockDeviceAPI <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/blockdevice.py>`_ interface.
Flocker itself provides a `loopback <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/blockdevice.py>`_ implementation (for testing, lacking data movement), `OpenStack Cinder <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/cinder.py>`_ and `Amazon EBS <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/ebs.py>`_; these can serve as examples of implementation.

Driver Prerequisites
====================

Driver needs support to store metadata for each volume on the storage backend.

Driver needs a way to programmatically map compute instance id to the input format expected by your storage backend for attach operation. For example, if you have a 2 node compute+storage cluster on AWS, and your storage solution refers to the compute nodes as ``aws1`` and ``aws2``, your driver running on ``aws1`` would need be able to find out its compute instance name as ``aws1``, not ``i-1cf275d9`` (EC2 naming convention).

Driver needs a way to request default storage features (like compression, dedup, IOPs, SSD/HDD) while creating a volume.

Please consider adding driver logs for debuggability.

Test Plan
=========

Step 1: Minimal functional tests

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

If you wish the tests to cleanup volumes after each run, please provide a cleanup version of ``IBlockDeviceAPI`` (for example, `EBS API with cleanup <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/test/blockdevicefactory.py#L225>`_) inside ``api_factory``.

You can run these tests with ``trial`` test runner provided by `Twisted <https://twistedmatrix.com/trac/>`_, one of Flocker's dependencies:

.. prompt:: bash $

    trial yourstorage.test_yourstorage

Step 2: Additional functional tests

You are encouraged to write additional functional tests to cover logic specific to your driver implementation. For example, here are some `EBS driver-specific tests<https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/functional/test_ebs.py#L155>`_ .

Step 3: Run acceptance tests

After all functional tests pass, please run acceptance tests according to `documentation <https://docs.clusterhq.com/en/1.3.0/gettinginvolved/acceptance-testing.html>`_ .

Step 4: Setup Continuous Integration environment for tests

After acceptance tests run clean, please set up CI environment for functional and acceptance tests for your driver. Fro example: `EBS functional tests:<http://build.clusterhq.com/builders/flocker%2Ffunctional%2Faws%2Fubuntu-14.04%2Fstorage-driver>`_ , and `EBS acceptance tests:<http://build.clusterhq.com/builders/flocker%2Facceptance%2Faws%2Fubuntu-14.04%2Faws>`_ .

Step 5: Production ready certification

Once CI test runs pass for a week, please assert driver as ready for production usage with Flocker.

Demo
====

After driver development clears acceptance tests, you can do an end-to-end demo using `MongoDB<https://docs.clusterhq.com/en/1.3.0/using/tutorial/index.html>`_ .


Publish Driver
==============

Completed driver can be published as ``Public`` repo on ``GitHub``. Please include ``LICENSE`` information in your driver repo. Example: `Flocker License<https://github.com/ClusterHQ/flocker/blob/master/LICENSE>`_ .

Using storage plugins
=====================

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

Driver Development FAQ
======================

Is dataset_id unique for each volume created?

Yes.

Is there some way to get the dataset_id from flocker given the blockdevice_id  specific to our driver?

No.

Does Flocker node agent cache any state?

No. The only state cached is in Flocker control agent.

After running functional tests, i see a lot of volumes leftover from test run. Is there a script to clean them up?

After each test case, `detach_destroy_volumes<https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/test/test_blockdevice.py#L209>`_ is run automatically to cleanup volumes created by the test case. This cleanup call is added as part of `get_blockdeviceapi_with_cleanup<https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/test/blockdevicefactory.py#L265>`_ .
Please use ``get_blockdeviceapi_with_cleanup`` in your test wrapper.

Do you have an easy way to view the logs?  i get a lot of output in journactl and it’s very difficult to track what all is happening.

Eliot-tree is the preferred way, but does not work at the moment due to `a bug<https://github.com/jonathanj/eliottree/issues/28>`_ . 


Troubleshooting FAQ
===================

My functional test failed. How do i go about debugging?

Start with Flocker node agent log (`/var/log/flocker/flocker-dataset-agent.log`). You can use `eliot-tree<https://github.com/jonathanj/eliottree>`_ to render the log in ASCII format. 

If the Flocker log looks ok, move on to storage driver log, then storage backend logs.

i see the following error in Flocker dataset agent log. How do i triage further?


.. code-block::
Command '['mount', '/dev/sdb', '/flocker/c39e7d1c-7c9e-6029-4c30-42ab8b44a991']' returned non-zero exit status 32


Please run the failed command from command line prompt - the cause of failure is most likely environment related, and not caused by bug in Flocker or Flocker Storage driver.

i see the following error while running acceptance tests:

.. image:: Flocker_Hedvig_Snapshot.png

Please check that you have configured Flocker CA certs as documented `here<https://docs.clusterhq.com/en/1.3.0/config/configuring-authentication.html>`_ .

My test environment is messed up, and i’d like to reset Flocker control service state. How do i do that?

Flocker control state is stored in `/var/lib/flocker/current_configuration.v1.json` on control compute node.
You can edit/remove the file to reduce/cleanup control service state:


.. code-block:: bash
systemctl stop flocker-control
rm /var/lib/flocker/current_configuration.v1.json
systemctl start flocker-control/

