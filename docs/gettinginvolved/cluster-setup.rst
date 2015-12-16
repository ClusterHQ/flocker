.. _cluster-setup:

=========================
Setting Up a Test Cluster
=========================

Flocker includes a tool for creating a cluster with automatically generated configuration for testing purposes.

.. prompt:: bash $

   admin/setup-cluster <options>


The :program:`admin/setup-cluster` script has several options:

.. program:: admin/setup-cluster

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
      If you want to use a branch in development, you probably only want to specify the branch.

.. option:: --build-server <buildserver>

   Specifies the base URL of the build server to install from.
   This is probably only useful when testing changes to the build server.

.. option:: --config-file <config-file>

   Specifies a YAML configuration file that contains provider specific configuration.
   See below for the required configuration options.

.. option:: --no-keep

   Destroy the cluster after creating it.
   This option is useful for testing the tool itself.

.. option:: --purpose <purpose>

   Specifies a string that describes the purpose of the cluster.
   This can be included into the metadata describing the cluster nodes and/or names of the nodes.

.. option:: --number-of-nodes <number>

   Specifies the number of nodes (machines) to create for use in the cluster.
   This option is only applicable if the nodes are created dynamically.

.. option:: --app-template <application-template-file>

   Specifies a YAML file that describes a single application.
   It must include a name of a Docker image to use as an application container and may include other parameters.

.. option:: --apps-per-node <number>

   Specifies the number of applications (containers) to start on each cluster node.
   If this is not specified or zero, then no applications will be started.

To see the supported values for each option, run:

.. prompt:: bash $

   admin/setup-cluster --help

Application Template
====================

The configuration file given for the ``--app-template`` parameter describes a single application.
At the very least it should specify a name of a Docker image to use for an application container.

.. code-block:: yaml

  image: "clusterhq/mongodb"
  volume:
    mountpoint: "/data/db"

See :doc:`../control/cli/application-config` for more details.
The ``--apps-per-node`` parameter specifies how many applications to start on each cluster node.

.. prompt:: bash $

  admin/setup-cluster \
    --distribution centos-7 \
    --provider rackspace \
    --config-file $PWD/cluster.yml \
    --number-of-nodes 2 \
    --app-template $PWD/application.yml \
    --apps-per-node 5

Note that all application instances will have exactly the same configuration.

Configuration File
==================

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

.. _cluster-setup-rackspace-config:

Rackspace
=========

To create a cluster on Rackspace, see :ref:`acceptance-testing-rackspace-config`.

.. prompt:: bash $

  admin/setup-cluster --distribution centos-7 --provider rackspace --config-file config.yml --number-of-nodes 2

.. _cluster-setup-aws-config:

AWS
===

To create a cluster on AWS, see :ref:`acceptance-testing-aws-config`.

.. prompt:: bash $

  admin/setup-cluster --distribution centos-7 --provider aws --config-file config.yml --number-of-nodes 2

.. _cluster-setup-managed-config:

Managed
=======

You can also create a cluster on existing "managed" nodes, see :ref:`acceptance-testing-managed-config`.

The ``--number-of-nodes`` parameter is not applicable to the ``managed`` provider as the nodes are created in advance.

.. prompt:: bash $

   admin/setup-cluster --distribution centos-7 --provider managed --config-file config.yml

If you create nodes without using the ``--no-keep`` option the command will print out the cluster configuration when it exits.
For example:

.. code-block:: console

   ./admin/setup-cluster \
     --distribution=centos-7 \
     --provider=aws \
     --dataset-backend=aws \
     --config-file=$PWD/cluster.yml \
     --branch=master \
     --flocker-version=''

   ...

   The following variables describe the cluster:
   export FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE=1073741824;
   export FLOCKER_ACCEPTANCE_CONTROL_NODE=54.159.119.143;
   export FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS='{"10.230.191.121": "54.158.225.35", "10.69.174.223": "54.159.119.143"}';
   export FLOCKER_ACCEPTANCE_VOLUME_BACKEND=aws;
   export FLOCKER_ACCEPTANCE_NUM_AGENT_NODES=2;
   export FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH=/tmp/tmpfvb3xV;
   Be sure to preserve the required files.

In this case you can copy and paste the ``FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS`` value directly into the configuration file. E.g.

.. code-block:: yaml

   managed:
     addresses:
       - ["10.230.191.121", "54.158.225.35"]
       - ["10.69.174.223", "54.159.119.143"]

And then run ``setup-cluster`` to create a new cluster on top of the same  nodes.
Or you can run, for example, the acceptance tests against the created cluster:

.. code-block:: console

   ./admin/run-acceptance-tests \
     --distribution=centos-7 \
     --provider=managed \
     --dataset-backend=aws \
     --config-file=$PWD/cluster.yml
     --branch=master \
     --flocker-version='' \
     flocker.acceptance.obsolete.test_containers.ContainerAPITests.test_create_container_with_ports

