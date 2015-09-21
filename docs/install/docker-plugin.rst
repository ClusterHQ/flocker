
========================================
Installing the Flocker Plugin for Docker
========================================

Before installing the Flocker plugin for Docker, you will need to have installed Flocker on some nodes, using the :ref:`node installation instructions <installing-flocker-node>`.

The Flocker plugin for Docker requires access to the Flocker REST API, and therefore you will need to create an API user certificate and key for a user named ``plugin`` on each node, as described in the :ref:`generate-api` instructions.
For example, you can use the ``flocker-ca`` command as below:

.. prompt:: bash $

   flocker-ca create-api-certificate plugin
   scp ./plugin.crt root@172.16.255.251:/etc/flocker/plugin.crt
   scp ./plugin.key root@172.16.255.251:/etc/flocker/plugin.key

Upload these files to :file:`/etc/flocker/plugin.key` and :file:`/etc/flocker/plugin.crt` on the nodes where you want to run the Flocker plugin for Docker.

You will also need to have Docker (at least version 1.8 or later) installed. For more information, see `the Docker installation instructions <https://docs.docker.com/>`_.

Now you can use the following instructions to install the Flocker plugin for Docker on each of the nodes in your cluster.

On CentOS 7
===========

On each of your Flocker nodes, install the Flocker plugin:

.. prompt:: bash $

   yum install -y clusterhq-flocker-docker-plugin
   systemctl enable flocker-docker-plugin
   systemctl start flocker-docker-plugin

The service can then be started, stopped, or restarted using ``systemctl``.
For example:

.. prompt:: bash $

   systemctl restart flocker-docker-plugin


On Ubuntu 14.04
===============

On Ubuntu, it's best to ensure that Docker is using the ``AUFS`` storage driver.

The easiest way to do this is to add a ``-s aufs`` option to the :file:`/etc/default/docker` file.
For example::

   DOCKER_OPTS="-s aufs"

On each of your Flocker nodes, install the Flocker plugin:

.. prompt:: bash $

   apt-get install clusterhq-flocker-docker-plugin

The service can be started, stopped, or restarted using ``service``.
For example:

.. prompt:: bash $

   service flocker-docker-plugin restart

Testing your installation
=========================

Once installed, two simple Docker tests can be run to verify that the plugin is working correctly with the Flocker agents:

.. prompt:: bash $

   docker run -v apples:/data --volume-driver flocker busybox sh -c "echo hello > /data/file.txt"
   docker run -v apples:/data --volume-driver flocker busybox sh -c "cat /data/file.txt"

In this example, the first command uses the Flocker plugin for Docker as the volume driver to create a named volume called ``apples``.

In the second command we are reattaching the same volume from the first container, and verifying that the data (``hello``) has been preserved.

Upgrading the plugin
====================

If you are upgrading from an earlier version of the plugin, make sure to stop the Docker daemon before doing so and then start it back up once the plugin has been upgraded.

Known limitations
=================

* You should not move a volume from one node to another unless you are sure no containers are using the volume.

  The Flocker plugin will not stop volumes from being migrated out from underneath a running container.
  It is possible that Docker or your orchestration tool will prevent this from happening, but Flocker itself does not.
* ``--volumes-from`` and equivalent Docker API calls will only work if both containers are on the same machine.

  Some orchestration frameworks may not schedule containers in a way that respects this restriction, so check before using ``--volumes-from``.
* We recommend only using named volumes when using the Flocker plugin.

  If you use volumes in your Docker run commands without specified names, anonymous volumes can be created.
  This occurs as Docker defines volume drivers for the entire run command, not per-volume.
