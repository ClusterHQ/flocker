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

To see the supported values for each option, run:

.. prompt:: bash $

   admin/setup-cluster --help

An example of how to run :program:`setup-cluster` would be:

.. prompt:: bash $

  admin/setup-cluster \
    --distribution centos-7 \
    --provider rackspace \
    --config-file $PWD/cluster.yml \
    --number-of-nodes 2 

Configuration File
==================

For the description of the configuration file format, see :ref:`acceptance-testing-configuration-file`.

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

==============================
Adding containers and datasets
==============================
To make it easier to re-use a test cluster and test under different configurations, Flocker provides a tool to create a certain number of datasets and containers per node.
Run the following command to deploy clusters and datasets:

.. prompt:: bash $

    benchmark/setup-cluster-containers <options>

The :program:`setup-cluster-containers` script has the following command line options:

.. program:: setup-cluster-containers`

.. option:: --app-template <application-template-file>

   Specifies a YAML file that describes a single application.
   It must include a name of a Docker image to use as an application container and may include other parameters.

.. option:: --apps-per-node <number>

   Specifies the number of applications (containers) to start on each cluster node.
   If this is not specified, one container and dataset per node will be created.

.. option:: --control-node <ip-address>

    Public IP address of the control node.

.. option:: --cert-directory <certificates-directory>

   Specifies a directory containing:

   - ``cluster.crt`` - a CA certificate file;
   - ``user.crt`` - a user certificate file; and
   - ``user.key`` - a user private key file.

.. option:: --wait <seconds>

   Specifies the timeout of waiting for the configuration changes to take effect
   or, in other words, for the cluster to converge.
   If this parameter is not set, then the program will wait up to two hours.

If :option:`--wait` is used the script waits for the deletions to take effect.
After the script successfully finishes the cluster should be in a converged state
with the requested containers and datasets.
If :option:`--wait` is not specified, then the script will wait for up to two hours.

Application Template
--------------------

The configuration file given for the ``--app-template`` parameter describes a single application.
At the very least it should specify a name of a Docker image to use for an application container.

.. code-block:: yaml

  image: "clusterhq/mongodb"
  volume:
    mountpoint: "/data/db"

See :ref:application-configuration for more details.
The ``--apps-per-node`` parameter specifies how many applications to start on each cluster node.

.. prompt:: bash $

  admin/setup-cluster-containers \
    --app-template $PWD/application.yml \
    --apps-per-node 5 \
    --control-node 52.52.52.52 \
    --cert-directory /etc/flocker/test_cluster1/

Note that all application instances will have exactly the same configuration.
In particular, multiple containers may fail to start if they use a common host resource (e.g. host ports).

=====================================
Cleaning Up the Cluster Configuration
=====================================

A cluster can be used to test various configurations.
There is a tool to delete all containers and datasets in the cluster,
so that it can be re-used for testing a different configuration.

.. prompt:: bash $

   admin/cleanup-cluster <options>


The :program:`admin/cleanup-cluster` script has several options:

.. program:: admin/cleanup-cluster

.. option:: --control-node <address>

   Specifies the internet address of the control node of the cluster.

.. option:: --cert-directory <directory>

   Specifies the directory that contains the cluster certificates.

.. option:: --wait <seconds>

   Specifies the timeout of waiting for the configuration changes to take effect
   or, in other words, for the cluster to converge.
   If this parameter is not set, then no waiting is done.

If :option:`--wait` is used the script waits for the deletions to take effect.
After the script successfully finishes the cluster should be in a converged state
with no containers and datasets.
If :option:`--wait` is not specified, then the script exits after the deletion
requests are acknowledged without waiting for the cluster to converge.
