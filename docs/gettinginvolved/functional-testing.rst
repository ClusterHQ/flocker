==================
Functional Testing
==================

The tests for the various cloud block device backends depend on access to credentials supplied from the environment.

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

AWS
===

The configuration stanza for the EBS backend looks as follows:

.. code:: yaml

   aws:
     access_key: <aws access key>
     secret_access_token: <aws secret access token>

To run the functional tests, run the following command:

.. prompt:: bash #

   FLOCKER_FUNCTIONAL_TEST=TRUE \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE=$HOME/acceptance.yml \
   FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER=aws \
   FLOCKER_FUNCTIONAL_TEST_AWS_AVAILABILITY_ZONE=<aws region> \
   trial --testmodule flocker/node/agents/ebs.py

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

The configuration stanza for an private OpenStack deployment is the same as Rackspace above, but ``auth_plugin`` should be included, which refers to an authentication plugin provided by ``python-keystoneclient``.

If required, you may need to add additional fields.
For more information, see :ref:`openstack-dataset-backend`.
