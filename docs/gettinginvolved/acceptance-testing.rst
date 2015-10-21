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

.. option:: --branch <branch>

   Specifies the branch repository from which to install packages.
   If this is not specified, packages will be installed from a release repository.
   The release repository may be a stable or unstable repository, and will be selected depending on the version to be installed.

.. option:: --flocker-version <version>

   Specifies the version of Flocker to install from the selected repository.
   If this is not specified (or is an empty string), the most recent version available in the repository will be installed.

   .. note::

      The build server merges forward before building packages, except on release branches.
      If you want to run the acceptance tests against a branch in development,
      you probably only want to specify the branch.

.. option:: --build-server <buildserver>

   Specifies the base URL of the build server to install from.
   This is probably only useful when testing changes to the build server.

.. option:: --config-file <config-file>

   Specifies a YAML configuration file that contains provider specific configuration.
   See below for the required configuration options.

.. option:: --keep

   Keep VMs around, if the tests fail.

.. option:: --no-pull

   Do not pull any Docker images when provisioning nodes.

To see the supported values for each option, run:

.. prompt:: bash $

   admin/run-acceptance-tests --help

Configuration File
------------------

.. This is pretty messy.
   FLOC-2090

The configuration file given for the ``--config-file`` parameter contains information about compute-resource providers and dataset configurations.
The contents and structure of the file are explained here.
:ref:`An example containing all of the sections<acceptance-testing-configuration>` is also provided.

The top-level object in the file is a mapping.
It may optionally contain a ``metadata`` key.
If it does and if the provider supports it,
the value should be a mapping and the contents will be added as metadata of the created nodes.

The top-level mapping must contain a ``storage-drivers`` item.
The value should be another mapping from names to dataset backend configuration mappings.
The names are primarily human-readable and meant for easy use with the ``--dataset-backend`` option.
In some cases,
the name may exactly match the name of one of the dataset backend implementations supported by Flocker.
If this is not the case,
the configuration mapping must exactly match the ``dataset`` configuration described for :ref:`enabling the Flocker agent service<agent-yml>`.

Any number of dataset backend configurations may be present.
The configuration with a key matching the value of the ``--dataset-backend`` parameter is used.
Nodes in the testing cluster are given this configuration.

The top-level mapping may also contain any number of computer-resource provider configurations.
These are used to provide required parameters to the cluster runner selected by the ``--provider`` option.
Configuration is loaded from the item in the top-level mapping with a key matching the value given to ``--provider``.

Vagrant
~~~~~~~

The Vagrant cluster runner does not require any configuration and so does not require an item in the configuration file.

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

  admin/run-acceptance-tests --distribution centos-7 --provider vagrant


.. _acceptance-testing-rackspace-config:

Rackspace
~~~~~~~~~

To run the acceptance tests on Rackspace, you need:

- a Rackspace account and the associated API key
- an ssh-key registered with the Rackspace account.

To use the Rackspace provider, the configuration file should include an item like:

.. code-block:: yaml

   rackspace:
     region: <rackspace region, e.g. "iad">
     username: <rackspace username>
     key: <access key>
     keyname: <ssh-key-name>

You will need a ssh agent running with access to the corresponding private key.

Rackspace can use these dataset backends:

* :ref:`OpenStack<openstack-dataset-backend>`.
* :ref:`ZFS<zfs-dataset-backend>`.
* :ref:`Loopback<loopback-dataset-backend>`.

.. prompt:: bash $

  admin/run-acceptance-tests --distribution centos-7 --provider rackspace --config-file config.yml


.. _acceptance-testing-aws-config:

AWS
~~~

To run the acceptance tests on AWS, you need:

- a AWS account and the associated API key
- an ssh-key registered with the AWS account.
- a permissive security group

.. code-block:: yaml

   aws:
     region: <aws region, e.g. "us-west-2">
     zone: <aws zone, e.g. "us-west-2a">
     access_key: <aws access key>
     secret_access_token: <aws secret access token>
     keyname: <ssh-key-name>
     security_groups: ["<permissive security group>"]

You will need a ssh agent running with access to the corresponding private key.

AWS can use these dataset backends:

* :ref:`AWS<aws-dataset-backend>`.
* :ref:`ZFS<zfs-dataset-backend>`.
* :ref:`Loopback<loopback-dataset-backend>`.

If you're using the AWS dataset backend make sure the regions and zones are the same both here and there!

.. prompt:: bash $

  admin/run-acceptance-tests --distribution centos-7 --provider aws --config-file config.yml

.. _acceptance-testing-managed-config:

Managed
~~~~~~~

You can also run acceptance tests on existing "managed" nodes.

This is a quicker way to run the acceptance tests as it avoids the slow process of provisioning new acceptance testing nodes.

The ``managed`` provider re-installs and restarts node related ``clusterhq-*`` packages and distributes new certificates and keys to all the nodes.

This means that the ``managed`` provider can be used to quickly test different package versions and packages built from different branches.

To use the ``managed`` provider, the configuration file should include:

- **addresses**: A ``list`` of IP addresses of the nodes or a ``dict`` of ``{"<private_address>": "<public_address>"}`` if the public addresses are not configured on the node (see below).
- **upgrade**: ``true`` to automatically upgrade Flocker before running the tests,
  ``false`` or missing to rely on the version already installed.

.. code-block:: yaml

   managed:
     addresses:
       - "192.0.2.101"
       - "192.0.2.102"

The nodes should be configured to allow key based SSH connections as user ``root`` and the ``root``.

.. prompt:: bash $

   admin/run-acceptance-tests --distribution centos-7 --provider managed --config-file config.yml

If you are using the ``managed`` provider with ``AWS`` nodes, you  will need to supply both the private and public IP addresses for each node.
AWS nodes do not have public IP addresses configured in the operating system; instead Amazon routes public IP traffic using NAT.
In this case the acceptance tests need a hint in order to map the private IP address reported by the Flocker ``/state/nodes`` API to the public node address.
E.g. When a test needs to verify that a container on the node is listening on an expected port or to communicate directly with the Docker API on that node.
The mapping is supplied to the tests in the ``FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS`` environment variable.

If you create nodes using ``run-acceptance-tests --runner=aws --keep`` the command will print out the node addresses when it exits. E.g.

.. code-block:: console

   ./admin/run-acceptance-tests \
     --keep \
     --distribution=centos-7 \
     --provider=aws \
     --dataset-backend=aws \
     --config-file=$PWD/acceptance.yml \
     --branch=master \
     --flocker-version='' \
     flocker.acceptance.obsolete.test_containers.ContainerAPITests.test_create_container_with_ports

   ...

   flocker.acceptance.obsolete.test_containers
     ContainerAPITests
       test_create_container_with_ports ...                                   [OK]

   -------------------------------------------------------------------------------
   Ran 1 tests in 14.102s

   PASSED (successes=1)
   --keep specified, not destroying nodes.
   To run acceptance tests against these nodes, set the following environment variables:

   export FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE=1073741824;
   export FLOCKER_ACCEPTANCE_CONTROL_NODE=54.159.119.143;
   export FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS='{"10.230.191.121": "54.158.225.35", "10.69.174.223": "54.159.119.143"}';
   export FLOCKER_ACCEPTANCE_VOLUME_BACKEND=aws;
   export FLOCKER_ACCEPTANCE_NUM_AGENT_NODES=2;
   export FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH=/tmp/tmpfvb3xV;

In this case you can copy and paste the ``FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS`` value directly into the configuration file. E.g.

.. code-block:: yaml

   managed:
     addresses:
       - ["10.230.191.121", "54.158.225.35"]
       - ["10.69.174.223", "54.159.119.143"]

And then run the acceptance tests on those nodes using the following command:

.. code-block:: console

   ./admin/run-acceptance-tests \
     --distribution=centos-7 \
     --provider=managed \
     --dataset-backend=aws \
     --config-file=$PWD/acceptance.yml
     --branch=master \
     --flocker-version='' \
     flocker.acceptance.obsolete.test_containers.ContainerAPITests.test_create_container_with_ports


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
