.. _acceptance-testing:

Acceptance Testing
==================

Flocker includes a number of acceptance tests and a tool for running them.
It needs the appropriate ssh-key added to a running ssh-agent.
It is called like this:

.. prompt:: bash $

   admin/run-acceptance-tests <options> [<test-cases>]


The :program:`admin/run-acceptance-tests` script has several options:

.. program:: admin/run-acceptance-tests

.. option:: --distribution <distribution>

   Specifies what distribution to use on the created nodes.

.. option:: --provider <provider>

   Specifies what provider to use to create the nodes.

.. option:: --dataset-backend <dataset-backend>

   Specifies what dataset backend to use for the cluster.

.. option:: --flocker-version <version>

   Specifies the version of flocker to install.
   If this isn't specified, the most recent version will be installed.
   If a branch is also specified, the most recent version from that branch will be installed.
   If a branch is not specified, the most recent release will be installed.

   .. note::

      The build server merges forward before building packages, except on release branches.
      If you want to run the acceptance tests against a branch in development,
      you probably only want to specify the branch.

.. option:: --branch <branch>

   Specifies the branch from which packages are installed.
   If this isn't specified, packages will be installed from the release repository.

.. option:: --build-server <buildserver>

   Specifies the base URL of the build server to install from.
   This is probably only useful when testing changes to the build server.

.. option:: --config-file <config-file>

   Specifies a YAML configuration file that contains provider specific configuration.
   See below for the required configuration options.
   If the configuration contains a ``metadata`` key,
   the contents will be added as metadata of the created nodes,
   if the provider supports it.

.. option:: --keep

   Keep VMs around, if the tests fail.

.. option:: --no-pull

   Do not pull any Docker images when provisioning nodes.

To see the supported values for each option, run:

.. prompt:: bash $

   admin/run-acceptance-tests --help


Vagrant
-------

A configuration file is not required for the vagrant provider.

You will need a ssh agent running with access to the insecure vagrant private key:

.. prompt:: bash $

  ssh-add ~/.vagrant.d/insecure_private_key


.. The following step will go away once FLOC-1163 is addressed.

You will also need the tutorial vagrant box BuildBot has created from the release branch.
The URL can be found by examining the "upload-base-box" step of the ``flocker-vagrant-tutorial-box`` builder.
The URL will look like ``http://build.clusterhq.com/results/vagrant/<branch>/flocker-tutorial.json``.

.. prompt:: bash $

   vagrant box add <URL>

Ensure that they all pass, with no skips:

.. prompt:: bash $

  admin/run-acceptance-tests --distribution fedora-20 --provider vagrant

Rackspace
---------

To run the acceptance tests on Rackspace, you need:

- a Rackspace account and the associated API key
- an ssh-key registered with the Rackspace account.

The configuration file for the Rackspace provider looks like:

.. code-block:: yaml

   rackspace:
     region: <rackspace region, e.g. "iad">
     username: <rackspace username>
     key: <access key>
     keyname: <ssh-key-name>
   metadata:
     creator: <your-name>

You will need a ssh agent running with access to the corresponding private key.

.. prompt:: bash $

  admin/run-acceptance-tests --distribution fedora-20 --provider rackspace --config-file config.yml


AWS
---

To run the acceptance tests on AWS, you need:

- a AWS account and the associated API key
- an ssh-key registered with the AWS account.
- a permissive security group

.. code-block:: yaml

   aws:
     region: <aws region, e.g. "us-west-2">
     access_key: <aws access key>
     secret_access_token: <aws secret access token>
     keyname: <ssh-key-name>
     security_groups: ["<permissive security group>"]
   metadata:
     creator: <your-name>

You will need a ssh agent running with access to the corresponding private key.

.. prompt:: bash $

  admin/run-acceptance-tests --distribution fedora-20 --provider aws --config-file config.yml


.. _client-acceptance-tests:

Client Testing
==============

Flocker includes client installation tests and a tool for running them.
It is called like this:

.. prompt:: bash $

   admin/run-cluster-tests <options> [<test-cases>]


The :program:`admin/run-client-tests` script has several options:

.. program:: admin/run-client-tests

.. option:: --distribution <distribution>

   Specifies what distribution to use on the created nodes.

.. option:: --provider <provider>

   Specifies what provider to use to create the nodes.

.. option:: --flocker-version <version>

   Specifies the version of flocker to install.
   If this isn't specified, the most recent version will be installed.
   If a branch is also specified, the most recent version from that branch will be installed.
   If a branch is not specified, the most recent release will be installed.

   .. note::

      The build server merges forward before building packages, except on release branches.
      If you want to run the acceptance tests against a branch in development,
      you probably only want to specify the branch.

.. option:: --branch <branch>

   Specifies the branch from which packages are installed.
   If this isn't specified, packages will be installed from the release repository.

.. option:: --build-server <buildserver>

   Specifies the base URL of the build server to install from.
   This is probably only useful when testing changes to the build server.

.. option:: --config-file <config-file>

   Specifies a YAML configuration file that contains provider specific configuration.
   See the acceptance testing section above for the required configuration options.
   If the configuration contains a ``metadata`` key,
   the contents will be added as metadata of the created nodes,
   if the provider supports it.

.. option:: --keep

   Keep VMs around, if the tests fail.

To see the supported values for each option, run:

.. prompt:: bash $

   admin/run-client-tests --help


Functional Testing
==================

The tests for the various cloud block device backends depend on access to credentials supplied from the environment.

The tests look for two environment variables:

- ``FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE``: This points at a yaml file with the credentials.
- ``FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER``: This is the name of a top-level key in the configuration file.

The credentials are read from the stanza specified by the ``CLOUD_PROVIDER`` environment variable.
The supported block-device backend is specified by a ``provider`` key in the stanza,
or the name of the stanza, if the ``provider`` key is missing.

If the environment variables aren't present, the tests will be skipped.
The tests that do not correspond to the configured provider will also be skipped.

AWS
---

The configuration stanza for the EBS backend looks as follows:

.. code:: yaml

   aws:
     access_key: <aws access key>
     secret_access_token: <aws secret access token>

The AWS backend also requires that the availability zone the test are running in be specified in the  ``FLOCKER_FUNCTIONAL_TEST_AWS_AVAILABILITY_ZONE`` environment variable.
This is specified separately from the credential file, so that the file can be reused in different regions.

Rackspace
---------

The configuration stanza for the OpenStack backend running on Rackspace looks as follows:

.. code:: yaml

   rackspace:
     region: <rackspace region, e.g. "iad">
     username: <rackspace username>
     key: <access key>

OpenStack
---------

The configuration stanza for an private OpenStack deployment looks as follows:

.. code:: yaml

   private-cloud:
     provider: openstack
     auth_plugin: plugin_name
     plugin_option: value

``auth_plugin`` refers to an authentication plugin provided by ``python-keystoneclient``.
