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

.. option:: --cert-directory <directory>

   If this option is used then the generated cluster certificate files will be stored
   in the directory specified.
   Otherwise a random temporary directory will be used.
   The specified directory must not exist or it must be an empty directory.

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

The :program:`setup-cluster` script also creates the following files in the directory
specified by :option:`--cert-directory`:

    :file:`environment.env`
        contains definitions of the environment variables that are needed to run the
        acceptance tests on the cluster.

    :file:`managed.yaml`
        a YAML configuration file based on the file specified with :option:`--config-file` that
        in addition contains a ``managed`` section describing the newly created cluster nodes.

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

.. _cluster-setup-gce-config:

GCE
===

To create a cluster on GCE, see :ref:`acceptance-testing-gce-config`.

.. prompt:: bash $

  admin/setup-cluster --distribution centos-7 --provider gce --dataset-backend gce --config-file config.yml --number-of-nodes 2

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

=========================
Extending a Cluster
=========================

It is possible to add more nodes to an existing Flocker cluster.

.. prompt:: bash $

   admin/add-cluster-nodes <options>


The :program:`admin/add-cluster-nodes` script has several options,
some of them the same as for :program:`admin/setup-cluster`:

.. program:: admin/add-cluster-nodes

.. option:: --distribution <distribution>

   See :program:`admin/setup-cluster`.
   Typically this would be the same distribution as for the existing cluster nodes,
   however that's not required.

.. option:: --provider <provider>

   See :program:`admin/setup-cluster`.
   This should be the same provider as for the existing nodes.
   The new nodes may fail to work properly otherwise.
   At present ``rackspace`` and ``aws`` providers are supported.

.. option:: --dataset-backend <dataset-backend>

   See :program:`admin/setup-cluster`.

.. option:: --branch <branch>

   See :program:`admin/setup-cluster`.
   Different Flocker versions might fail to inter-operate.

.. option:: --flocker-version <version>

   See :program:`admin/setup-cluster`.
   Different Flocker versions might fail to inter-operate.

.. option:: --build-server <buildserver>

   See :program:`admin/setup-cluster`.

.. option:: --config-file <config-file>

   See :program:`admin/setup-cluster`.
   The configuration file must include a ``managed`` section that describes the existing nodes.
   Typically this would be :file:`managed.yaml` file from the certificates directory
   of the cluster.  See :option:`--cert-directory`.

.. option:: --purpose <purpose>

   See :program:`admin/setup-cluster`.
   The purpose should be the same as used when creating the existing node.
   That makes the administration of the nodes easier.

.. option:: --tag <tag>

   :program:`admin/setup-cluster` generates a random tag that is added to names
   of the cluster nodes.
   This option allows to use the same tag for the new nodes.
   That makes the administration of the nodes easier.

.. option:: --number-of-nodes <number>

   Specifies the number of additional nodes to add to the cluster.

.. option:: --cert-directory <directory>

   This mandatory option specifies a directory with the cluster certificate files.
   Certificate files for the new nodes will also be added to this directory.
   The :file:`environment.env` and :file:`managed.yaml` files in this directory will
   be updated in place.

.. option:: --control-node <IP address>

   IP address of the cluster's control node.

.. option:: --starting-index <number>

   A starting index to use when naming the new nodes.
   If not specified then the number of the existing nodes will be used as the starting index.
   The indexes of nodes are reflected in their names and in file names of node certificates.


:program:`add-cluster-nodes` may create fewer nodes than requested with :option:`--number-of-nodes`,
the partial success is still considered as a success.
A diagnostic message will be printed in such a case.

To see the supported values for each option, run:

.. prompt:: bash $

   admin/add-cluster-nodes --help

An example of how to run :program:`add-cluster-nodes` would be:

.. prompt:: bash $

  admin/add-cluster-nodes \
    --distribution centos-7 \
    --branch master \
    --config-file ~/clusters/test0/managed.yaml \
    --purpose FLOC-3947 \
    --tag '4S4Av0gRJ9c' \
    --cert-directory ~/clusters/test0 \
    --control-node 52.33.228.33 \
    --number-of-nodes 3

Adding Containers and Datasets
==============================

To make it easier to re-use a test cluster and test under different configurations, Flocker provides a tool to create a certain number of datasets and containers per node.
Run the following command to deploy clusters and datasets:

.. prompt:: bash $

    benchmark/setup-cluster-containers <options>

The :program:`setup-cluster-containers` script has the following command line options:

.. program:: setup-cluster-containers`

.. option:: --image <docker image>

   Specifies the docker image to use to create the containers.

.. option:: --mountpoint <mountpoint path>

    Path of the mountpoint where the dataset should be mounted in the containers.

.. option:: --control-node <ip-address>

    Public IP address of the control node.

.. option:: --apps-per-node <number>

   Specifies the number of applications (containers) to start on each cluster node.
   If this is not specified, one container and dataset per node will be created.

.. option:: --cert-directory <certificates-directory>

   Specifies a directory containing:

   - ``cluster.crt`` - a CA certificate file;
   - ``user.crt`` - a user certificate file; and
   - ``user.key`` - a user private key file.

.. option:: --max-size <GB>
    
    Maximum size of the datasets specified in gigabytes. This parameter is optional. By default it will
    be 1GB.

.. option:: --wait <seconds>

   Specifies the timeout of waiting for the configuration changes to take effect
   or, in other words, for the cluster to converge.
   If this parameter is not set, then the program will wait up to two hours.

.. option:: --wait-interval <seconds>
    
    The duration of the waiting intervals can be set as a parameter. It will determine how long the
    program will wait between list calls when waiting for the containers and datasets to be created.
    It is four seconds by default.

If :option:`--max-size` is used the script will create volumes with the given maximum
size (GB).
If :option:`--max-size` is not specified, then the script will create volumes of 1GB.

If :option:`--wait` is used the script waits for the deletions to take effect.
After the script successfully finishes the cluster should be in a converged state
with the requested containers and datasets.
If :option:`--wait` is not specified, then the script will wait for up to two hours.

If :option:`--wait-interval` is used the script waits the specified number of seconds between
list calls when waiting for the containers and datasets to be created.
If :option:`--wait-interval` is not specified, then the script will wait for four seconds.

An example of how to use it, without specifying any optional argument would be:

.. prompt:: bash $

  benchmark/setup-cluster-containers \
    --image "clusterhq/mongodb" \
    --mountpoint "/data/db" \
    --apps-per-node 5 \
    --control-node 52.52.52.52 \
    --cert-directory /etc/flocker/test_cluster1/

Note that all application instances will have exactly the same configuration.
In particular, multiple containers may fail to start if they use a common host resource (e.g. host ports).

Cleaning Up the Cluster Configuration
=====================================

A cluster can be used to test various configurations.
There is a tool to delete all containers and datasets in the cluster,
so that it can be re-used for testing a different configuration.

.. prompt:: bash $

   benchmark/cleanup-cluster <options>


The :program:`benchmark/cleanup-cluster` script has several options:

.. program:: benchmark/cleanup-cluster

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
