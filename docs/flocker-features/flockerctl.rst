.. _labs-volumes-cli:

.. _flockerctl:

==========================
The ``flockerctl`` Command
==========================

.. raw:: html

    <div class="admonition labs">
        <p>This page describes one of our experimental projects, developed to less rigorous quality and testing standards than the mainline Flocker distribution. It is not built with production-readiness in mind.</p>
        </div>

``flockerctl`` is a CLI for controlling the Flocker Control Service, with commands for listing nodes, creating volumes, and moving them around.
``flockerctl`` supports supplying metadata such as size, name and :ref:`storage-profiles`.

Install & Configure
===================

Run the following command to install ``flockerctl``:

.. prompt:: bash $

   curl -sSL https://get.flocker.io |sh

You will need to set some environment variables which define the address and credentials that ``flockerctl`` will use to connect to the Flocker control service:

* ``FLOCKER_CERTS_PATH`` - typically ``/etc/flocker`` if you're running ``flockerctl`` from a node in the cluster, otherwise, where your certificates are stored.
* ``FLOCKER_USER`` - the name of a flocker user which has ``.key`` and ``.crt`` file in the certs path. See :ref:`generate-api-standalone-flocker`.
* ``FLOCKER_CONTROL_SERVICE`` - the address (DNS name or IP address) of the control service. The name you use should match up with the name you specified when creating the cluster certificates.


Running the CLI
===============

The command for the CLI tool is ``flockerctl``.  If you run this command in the same folder as your ``cluster.yml`` file - it will use the settings in the file.  If you run it from elsewhere - you need to tell the CLI some additional options.

Here is the output of the ``flockerctl --help`` command, where you can see the supported options::

    $ flockerctl --help
    Usage: flockerctl [options]
    Options:
          --cluster-yml=      Location of cluster.yml file (makes other options
                              unnecessary) [default: ./cluster.yml]
          --certs-path=       Path to certificates folder [default: .]
          --user=             Name of user for which .key and .crt files exist
                              [default: user]
          --cluster-crt=      Name of cluster cert file [default: cluster.crt]
          --control-service=  Hostname or IP of control service
          --control-port=     Port for control service REST API [default: 4523]
          --version           Display Twisted version and exit.
          --help              Display this help and exit.
    Commands:
        create          create a flocker dataset
        destroy         mark a dataset to be deleted
        list            list flocker datasets
        list-nodes      show list of nodes in the cluster
        move            move a dataset from one node to another
        version         show version information

So - to test that the CLI is installed properly - we can do this command:

.. prompt:: bash $

    flockerctl --version

Listing Nodes
=============

You can list the nodes in your cluster using this command:

.. prompt:: bash $

    flockerctl list-nodes

It will produce output like this::

    SERVER     ADDRESS
    1acbab49   172.16.70.251
    5d74f5be   172.16.70.250

This shows short ID's for the nodes.  To show the full ID's for each node:

.. prompt:: bash $

    flockerctl list-nodes -l

It will produce output like this::

    SERVER                                 ADDRESS
    1acbab49-877c-40d4-80c6-a78ba581df7a   172.16.70.251
    5d74f5be-0422-433f-8c6e-dc31f9d89565   172.16.70.250

Here is the output of the help for ``list-nodes``

.. prompt:: bash $

    flockerctl list-nodes --help

It will produce output like this::

    Options:
    -l, --long     Show long UUIDs
        --version  Display Twisted version and exit.
        --help     Display this help and exit.

Creating a Volume
=================

To create a volume you tell the CLI the ID of the node you want it attached to, the maximum size and some optional metadata.

Here is an example of a CLI command to create a volume:

.. prompt:: bash $

    flockerctl create \
        --node 1acbab49 \
        --size 50Gb \
        --metadata "name=apples,size=medium"

The above command will create a volume that is targeted to the ``172.16.70.251`` node (using it's ID).

The node property instructs Flocker to attach the volume to the given node, use the ID of the node you want the volume attached to.
The size property can either be a number (meaning bytes) or you can use ``Gb`` or ``Mb``.
The metadata property is a comma-separated string of ``key=value`` pairs.

Here is the output of the help for ``create``

.. prompt:: bash $

    flockerctl create --help

It will produce output like this::

    Usage: flockerctl [options] create [options]
    Options:
      -n, --node=      Initial primary node for dataset (any unique prefix of node
                       uuid, see flockerctl list-nodes)
      -m, --metadata=  Set volume metadata ("a=b,c=d")
      -s, --size=      Set size in bytes (default), k, M, G, T
          --version    Display Twisted version and exit.
          --help       Display this help and exit.

Listing Volumes
===============

To list the volumes in your cluster - use the ``list`` command::

    $ flockerctl list
    DATASET                                SIZE      METADATA                  STATUS         SERVER
    9026a6f5-8c74-485d-84a9-a8b41e5b8e66   50.00G    name=apples,size=medium   attached       1acbab49 (172.16.70.251)
    b180f7bb-71f4-4acd-82c7-20f4bbd80a21   100.00G   name=apples               attached       1acbab49 (172.16.70.251)

Here is the output of the help for ``list``

.. prompt:: bash $

    flockerctl list --help

It will produce output like this::

    Usage: flockerctl [options] list [options]
    Options:
      -d, --deleted  Show deleted datasets
      -l, --long     Show long UUIDs
      -h, --human    Human readable numbers
          --version  Display Twisted version and exit.
          --help     Display this help and exit.

Moving Volumes
==============

To move a volume from one node to another - use the ``move`` command.

.. prompt:: bash $

    flockerctl move \
        --dataset 9026a6f5 \
        --target 5d74f5be

This command would move the ``9026a6f5`` dataset onto node ``5d74f5be``

Here is the output of the help for ``move``

.. prompt:: bash $

    flockerctl move --help

It will produce output like this::

    Usage: flockerctl [options] move [options]
    Options:
      -d, --dataset=      Dataset to move (uuid)
      -t, --destination=  New primary node (uuid) to move the dataset to
          --version       Display Twisted version and exit.
          --help          Display this help and exit.


Destroying Volumes
==================

To mark a volume as destroyed - use the ``destroy`` command.

.. prompt:: bash $

    flockerctl destroy \
        --dataset 9026a6f5

This command would destroy the ``9026a6f5`` dataset.

Here is the output of the help for ``destroy``.

.. prompt:: bash $

    flockerctl destroy --help

It will produce output like this::

    Usage: flockerctl [options] destroy [options]
    Options:
      -d, --dataset=  Dataset to destroy
          --version   Display Twisted version and exit.
          --help      Display this help and exit.
