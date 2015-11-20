==================
Functional Testing
==================

The tests for the various cloud block device backends depend on access to credentials supplied from the environment.

The tests look for two environment variables:
  ..
     # FLOC-2090 This is yet another configuration file.
     # Make it just be the same as the acceptance testing configuration file.

- ``FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE``: This points at a YAML file with the credentials.
- ``FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER``: This is the name of a top-level key in the configuration file.

The credentials are read from the stanza specified by the ``CLOUD_PROVIDER`` environment variable.
The supported block-device backend is specified by a ``provider`` key in the stanza,
or the name of the stanza, if the ``provider`` key is missing.

If the environment variables aren't present, the tests will be skipped.
The tests that do not correspond to the configured provider will also be skipped.

AWS
===

The configuration stanza for the EBS backend looks as follows:

.. code:: yaml

   aws:
     access_key: <aws access key>
     secret_access_token: <aws secret access token>

The AWS backend also requires that the availability zone the test are running in be specified in the  ``FLOCKER_FUNCTIONAL_TEST_AWS_AVAILABILITY_ZONE`` environment variable.
This is specified separately from the credential file, so that the file can be reused in different regions.

Rackspace
=========

The configuration stanza for the OpenStack backend running on Rackspace looks as follows:

.. code:: yaml

   rackspace:
     region: <rackspace region, e.g. "iad">
     username: <rackspace username>
     key: <access key>

OpenStack
=========

The configuration stanza for an private OpenStack deployment looks as follows:

.. code:: yaml

   private-cloud:
     provider: openstack
     auth_plugin: plugin_name
     plugin_option: value

``auth_plugin`` refers to an authentication plugin provided by ``python-keystoneclient``.
