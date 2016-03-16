==================
Functional Testing
==================

The tests for the various cloud block device backends depend on access to credentials supplied from the environment.

These tests must be run from an instance of the cloud provider.
For example, to run the EBS functional tests, you will need to run the tests from an EC2 instance.

The tests look for the following environment variables:

.. XXX
     # FLOC-2090 This is yet another configuration file.
     # Make it just be the same as the acceptance testing configuration file.

- ``FLOCKER_FUNCTIONAL_TEST``:
  This variable must be set.
- ``FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE``:
  This variable points at a YAML file with the credentials.
- ``FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER``:
  This variable must be the name of a top-level key in the configuration file.
- ``FLOCKER_FUNCTIONAL_TEST_AWS_AVAILABILITY_ZONE`` (AWS only):
  The AWS backend requires that the availability zone that the test is running in to be specified.
  This is specified separately from the credential file, so that the file can be reused in different regions.
- ``FLOCKER_FUNCTIONAL_TEST_OPENSTACK_REGION`` (Rackspace and OpenStack only):
  The Rackspace and OpenStack backends require that the region that the test is running in to be specified.
  This is specified separately from the credential file, so that the file can be reused in different regions.

The credentials are read from the stanza specified by the ``FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER`` environment variable.
The supported block-device backend is specified by a ``provider`` key in the stanza,
or the name of the stanza, if the ``provider`` key is missing.

If the environment variables are not present, the tests will be skipped.
The tests that do not correspond to the configured provider will also be skipped.

Setting up the Flocker environment
==================================

To run the functional tests, you will need to set up a Flocker development environment on your cloud instance.

To install this environment on CentOS, run the following commands:

.. prompt:: bash

   yum install python-devel openssl-devel git libffi-devel python-pip
   yum groupinstall "Development tools"
   pip install virtualenvwrapper
   source /usr/bin/virtualenvwrapper.sh
   mkvirtualenv flocker
   git clone https://github.com/ClusterHQ/flocker
   cd flocker/
   pip install -e .[dev]

Or for Ubuntu:

.. prompt:: bash

   apt-get install python-dev libssl-dev git libffi-dev python-pip
   pip install virtualenvwrapper
   source /usr/local/bin/virtualenvwrapper.sh
   mkvirtualenv flocker
   git clone https://github.com/ClusterHQ/flocker
   cd flocker/
   pip install -e .[dev]

AWS
===

The configuration stanza for the EBS backend looks as follows:

.. code:: yaml

   aws:
     access_key: <aws access key>
     secret_access_token: <aws secret access token>

Now run the following command to set up the environment and run the tests:

.. prompt:: bash #

   FLOCKER_FUNCTIONAL_TEST=TRUE \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE=$HOME/acceptance.yml \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER=aws \
   FLOCKER_FUNCTIONAL_TEST_AWS_AVAILABILITY_ZONE=<aws region> \
   trial --testmodule flocker/node/agents/ebs.py

GCE
===

The configuration stanza for the GCE backend is currently empty. Instead of
putting the credentials here, the GCE functional tests assume that they are
running on an instance that has been started with service account permissions
to have API access to the Google Cloud services in the same project.

Note that due to common code in the functional tests you still must have the
following configuration stanza despite it being empty.

.. code:: yaml

   gce: {}

Now run the following command to set up the environment and run the tests:

.. prompt:: bash #

   FLOCKER_FUNCTIONAL_TEST=TRUE \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE=$HOME/acceptance.yml \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER=gce \
   trial flocker.node.agents.functional.test_gce

Rackspace
=========

The configuration stanza for the OpenStack backend running on Rackspace looks as follows:

.. code:: yaml

   openstack:
     username: "<rackspace username>"
     api_key: "<access key>"
     auth_plugin: "rackspace"
     auth_url: "https://identity.api.rackspacecloud.com/v2.0"

To run the functional tests, run the following command:

.. prompt:: bash #

   FLOCKER_FUNCTIONAL_TEST=TRUE \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE=$HOME/acceptance.yml \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER=openstack \
   FLOCKER_FUNCTIONAL_TEST_OPENSTACK_REGION=<rackspace region> \
   trial --testmodule flocker/node/agents/cinder.py

OpenStack
=========

The configuration stanza for a private OpenStack deployment is similar to Rackspace (above), with a few notable differences:

* ``auth_plugin`` should be included, which refers to an authentication plugin provided by ``python-keystoneclient``.
* ``provider: "openstack"`` should be included, if the top level key is not ``openstack``.

If required, you may need to add additional fields.
For more information, see :ref:`openstack-dataset-backend`.

DevStack
--------

It is assumed that you have a working DevStack environment.
Refer to document "Setting up a DevStack instance" on Google Drive.

To run the Cinder functional tests on DevStack:

* Boot a supported guest operating system in DevStack.
* Log into the guest and clone your branch of the Flocker source code.
* Install the Flocker dependencies in a ``virtualenv``.
* Create ``$HOME/acceptance.yml`` containing:

.. code:: yaml

   # It is important to use ``devstack-openstack`` as the top-level name
   # because this limits the size of the Cinder volumes created in the tests to
   # 1 GiB.
   devstack-openstack:
     auth_plugin: password
     username: "<DevStack username e.g. admin>"
     password: "<DevStack password>"
     tenant_name: "<DevStack project name e.g. demo>"
     auth_url: "<DevStack keystone server endpoint e.g. http://192.0.2.100:5000/v2.0>"
     # This is important, so that the tests know to load the OpenStack Cinder
     # driver despite not using ``openstack`` as the top-level name.
     provider: "openstack"

* Run trial as ``root``:

.. prompt:: bash #

   FLOCKER_FUNCTIONAL_TEST=TRUE \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE=$HOME/acceptance.yml \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER=devstack-openstack \
   trial --testmodule flocker/node/agents/cinder.py
