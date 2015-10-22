.. _labs-volumes-cli:

=====================
Prototype Volumes CLI
=====================

Flocker includes a powerful volumes API.
However it does not yet include a native CLI.

This prototype demonstrates such a CLI, which has simple commands for listing nodes, creating volumes, and moving them around.
This can be used in conjunction with the Flocker Docker plugin, see :ref:`this demo <labs-demo>` (the volumes CLI makes an appearance at the end).

Install & Configure
===================

First, you need to :ref:`install Flocker <labs-installer>`, you can use our experimental :ref:`Flocker Installer <labs-installer>` to do this.
The Flocker Volumes CLI will be installed as part of this process, called ``flocker-volumes``.

To connect to the Flocker Control Service, the CLI will need a ``cluster.yml`` file that describes your cluster.
It will also need access to the TLS certificates that were created when you provisioned your cluster.

If you have used our :ref:`installer tool <labs-installer>` - you will have already created such a file.  The TLS certificates will have been generated in the same folder after you have run the ``flocker-config`` command.

You can read more about generating these certificates in the documentation for our :ref:`Flocker installer <labs-installer-certs-directory>`.

Running the CLI
===============

The command for the CLI tool is ``flocker-volumes``.  If you run this command in the same folder as your ``cluster.yml`` file - it will use the settings in the file.  If you run it from elsewhere - you need to tell the CLI some additional options.

Here is the output of the ``flocker-volumes --help`` command, where you can see the supported options::

    $ flocker-volumes --help
    Usage: flocker-volumes [options]
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

    flocker-volumes --version

Listing Nodes
=============

You can list the nodes in your cluster using this command:

.. prompt:: bash $

    flocker-volumes list-nodes

It will produce output like this::

    SERVER     ADDRESS
    1acbab49   172.16.70.251
    5d74f5be   172.16.70.250

This shows short ID's for the nodes.  To show the full ID's for each node:

.. prompt:: bash $

    flocker-volumes list-nodes -l

It will produce output like this::

    SERVER                                 ADDRESS
    1acbab49-877c-40d4-80c6-a78ba581df7a   172.16.70.251
    5d74f5be-0422-433f-8c6e-dc31f9d89565   172.16.70.250

Here is the output of the help for ``list-nodes``

.. prompt:: bash $

    flocker-volumes list-nodes --help

It will produce output like this::

    Options:
    -l, --long     Show long UUIDs
        --version  Display Twisted version and exit.
        --help     Display this help and exit.

Create a Volume
===============

To create a volume you tell the CLI the ID of the node you want it attached to, the maximum size and some optional metadata.

Here is an example of a CLI command to create a volume:

.. prompt:: bash $

    flocker-volumes create \
        --node 1acbab49 \
        --size 50Gb \
        --metadata "name=apples,size=medium"

The above command will create a volume that is targeted to the ``172.16.70.251`` node (using it's ID).

The node property instructs Flocker to attach the volume to the given node, use the ID of the node you want the volume attached to.
The size property can either be a number (meaning bytes) or you can use ``Gb`` or ``Mb``.
The metadata property is a comma-separated string of ``key=value`` pairs.

Here is the output of the help for ``create``

.. prompt:: bash $

    flocker-volumes create --help

It will produce output like this::

    Usage: flocker-volumes [options] create [options]
    Options:
      -n, --node=      Initial primary node for dataset (any unique prefix of node
                       uuid, see flocker-volumes list-nodes)
      -m, --metadata=  Set volume metadata ("a=b,c=d")
      -s, --size=      Set size in bytes (default), k, M, G, T
          --version    Display Twisted version and exit.
          --help       Display this help and exit.

List Volumes
============

To list the volumes in your cluster - use the ``list`` command::

    $ flocker-volumes list
    DATASET                                SIZE      METADATA                  STATUS         SERVER
    9026a6f5-8c74-485d-84a9-a8b41e5b8e66   50.00G    name=apples,size=medium   attached       1acbab49 (172.16.70.251)
    b180f7bb-71f4-4acd-82c7-20f4bbd80a21   100.00G   name=apples               attached       1acbab49 (172.16.70.251)

Here is the output of the help for ``list``

.. prompt:: bash $

    flocker-volumes list --help

It will produce output like this::

    Usage: flocker-volumes [options] list [options]
    Options:
      -d, --deleted  Show deleted datasets
      -l, --long     Show long UUIDs
      -h, --human    Human readable numbers
          --version  Display Twisted version and exit.
          --help     Display this help and exit.

Move Volumes
============

To move a volume from one node to another - use the ``move`` command.

.. prompt:: bash $

    flocker-volumes move \
        --dataset 9026a6f5 \
        --target 5d74f5be

This command would move the ``9026a6f5`` dataset onto node ``5d74f5be``

Here is the output of the help for ``move``

.. prompt:: bash $

    flocker-volumes move --help

It will produce output like this::

    Usage: flocker-volumes [options] move [options]
    Options:
      -d, --dataset=      Dataset to move (uuid)
      -t, --destination=  New primary node (uuid) to move the dataset to
          --version       Display Twisted version and exit.
          --help          Display this help and exit.


Destroy Volumes
===============

To mark a volume as destroyed - use the ``destroy`` command.

.. prompt:: bash $

    flocker-volumes destroy \
        --dataset 9026a6f5

This command would destroy the ``9026a6f5`` dataset.

Here is the output of the help for ``destroy``.

.. prompt:: bash $

    flocker-volumes destroy --help

It will produce output like this::

    Usage: flocker-volumes [options] destroy [options]
    Options:
      -d, --dataset=  Dataset to destroy
          --version   Display Twisted version and exit.
          --help      Display this help and exit.
