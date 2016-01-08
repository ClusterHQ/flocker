.. _build-flocker-driver:

================================
Building and Testing Your Driver
================================

This document will show you how to implement a Flocker storage driver.
Your driver will be a Python 2.7 library providing a class implementing the `flocker.node.agents.blockdevice.IBlockDeviceAPI <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/blockdevice.py>`_ interface.

The best way to build your driver is to model it on the canonical implementations provided by the ClusterHQ team.
These drivers include:

* `OpenStack Cinder <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/cinder.py>`_
* `Amazon EBS <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/ebs.py>`_

After you have implemented the driver, you will need to test your implementation, and ClusterHQ provide a number of test suites to help you do this.
These tests are the bare minimum required to accept the driver.
Other tests may be required that are specific to your design choices and driver implementation that cannot be covered by the test suites provided by ClusterHQ.
We highly encourage driver developers to write additional tests for these cases before your driver is ready to be deployed with Flocker in a customer environment.

Before beginning the testing steps below, you can review our :ref:`build-flocker-driver-faq` for common issues encountered during driver development and testing.

Testing Your Driver
===================

#. Implement minimal functional tests:

   To test that your implementation is correct you should instantiate a generic test suite that makes sure your class correctly implements the interface:

   .. code-block:: python

      from uuid import uuid4
      from flocker.node.agents.test.test_blockdevice import make_iblockdeviceapi_tests

      def api_factory(test):
          # Return an instance of your IBlockDeviceAPI implementation class, given
          # a twisted.trial.unittest.TestCase instance.

      # Smallest volume to create in tests, e.g. 1GiB:
      MIN_ALLOCATION_SIZE = 1024 * 1024 * 1024

      # Minimal unit of volume allocation, e.g. 1MiB:
      MIN_ALLOCATION_UNIT = 1024 * 1024

      class YourStorageTests(make_iblockdeviceapi_tests(
          api_factory, MIN_ALLOCATION_SIZE, MIN_ALLOCATION_UNIT,
          # Factory for valid but unknown volume id specific to your backend:
          lambda test: unicode(uuid4()))):
          """
          Tests for your storage.
          """

   If you wish the tests to cleanup volumes after each run, please provide a cleanup version of ``IBlockDeviceAPI``.
   For an example of a clean up script, see the `EBS API with cleanup <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/test/blockdevicefactory.py>`_ inside ``api_factory``.

   You can run these tests with the ``trial`` test runner, provided by `Twisted <http://twistedmatrix.com/trac/wiki/TwistedTrial>`_, one of Flocker's dependencies:

   .. prompt:: bash $

      trial yourstorage.test_yourstorage

#. Additional functional tests:

   You are encouraged to write additional functional tests to cover logic specific to your driver implementation.
   For example, here are some `EBS driver-specific tests <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/functional/test_ebs.py>`_ written by ClusterHQ.

#. Run acceptance tests:

   After all functional tests pass, please run acceptance tests according to our :ref:`acceptance-testing` documentation.
   Make sure you configure the acceptance test environment to use your new backend.

#. Setup a Continuous Integration environment for tests.

   After your acceptance tests pass, we recommend you set up a CI environment for functional and acceptance tests for your driver.


Enabling Flocker Users to Install Your Storage Driver
=====================================================

Once you've implemented your storage backend you'll want to allow Flocker users to use your package.
The basic implementation strategy is that your user installs a Python package with your backend implementation on all Flocker nodes:

.. prompt:: bash $

    /opt/flocker/bin/pip install https://example.com/your/storageplugin-1.0.tar.gz

You can also provide RPMs or DEBs that have same effect of installing a new Python package.

.. XXX FLOC-3143 will provide instructions for creating RPMs and DEBs

Once your users have installed the package, you should instruct your users to write an :file:`agent.yml` file (:file:`/etc/flocker/agent.yml`), whose ``backend`` key in the ``dataset`` section is the importable name of the Python package you've installed.

All other sub-keys of the ``dataset`` section will be passed to a function you must implement (see below), and can be used to configure the resulting ``IBlockDeviceAPI`` instance.

Typical parameters are authentication information or server addresses; whatever is necessary to configure your class.

For example, if you installed a Python package which is importable as ``mystorage_flocker_plugin``, and you require a username and password in order to log in to your storage system, you could tell your users to write a :file:`agent.yml` that looks like this:

.. code-block:: yaml

   version: 1
     control-service:
       hostname: "user.controlserver.example.com"
     dataset:
       backend: "mystorage_flocker_plugin"
       username: "username_for_mystorage"
       password: "abc123"

Your :file:`mystorage_flocker_plugin/__init__.py` module needs to have a ``FLOCKER_BACKEND`` attribute with a ``flocker.node.BackendDescription`` instance, which will include a reference to factory function that constructs a ``IBlockDeviceAPI`` instance.

The factory function will be called with whatever parameters the ``dataset`` section in :file:`agent.yml` is configured with.
In the above example, that would be ``username`` and ``password``.

Here's what the module could look like:

.. code-block:: python

    from flocker.node import BackendDescription, DeployerType
    from mystorage_flocker_plugin._backend import MyStorageAPI

    def api_factory(cluster_id, **kwargs):
        return MyStorageAPI(cluster_id=cluster_id, username=kwargs[u"username"],
                            password=kwargs[u"password"])

    FLOCKER_BACKEND = BackendDescription(
        name=u"mystorage_flocker_plugin",
        needs_reactor=False, needs_cluster_id=True,
        api_factory=api_factory, deployer_type=DeployerType.block)

The ``cluster_id`` parameter is a Python :py:obj:`uuid.UUID` instance uniquely identifying the cluster.
This is useful if you want to build a system that supports multiple Flocker clusters talking to a shared storage backend.

Make sure that your factory function raises an exception if it is given incorrect or insufficient parameters, so that users can easily see when they have mis-configured your backend.

.. XXX FLOC-3461 might suggest using ``UsageError`` exceptions, or some other more specific suggestion.

Publishing Your Driver
======================

Once your CI tests are running and passing successfully, you are ready to publish your driver and assert that it is certified to work with Flocker.

Completed drivers should be published as open source, publicly available source code, e.g. a ``Public`` repository on GitHub.

Please include the Apache 2.0 License as part of the repository.
For example, see the `Flocker License <https://github.com/ClusterHQ/flocker/blob/master/LICENSE>`_ .


Certifying Your Driver
======================

To demonstrate that your driver passes all tests, we recommend you include a Build Status badge at the top of the ``README`` on your driver's GitHub repository.

Examples of status images include `Travis CI <http://docs.travis-ci.com/user/status-images/>`_ and `Jenkins <https://wiki.jenkins-ci.org/display/JENKINS/Embeddable+Build+Status+Plugin>`_.

You should also clearly indicate which version of Flocker your driver has been certified against.


What's Next?
============

We recommend a demo to show off your hard work!

After driver development clears all tests and you've published getting-started instructions for your users, we recommend a video which you can use to share with others how they can build a Dockerized application using your storage backend.
