.. _install-docker-plugin:

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

Make sure your nodes are running Docker 1.8 or later.
For more information, see `the Docker installation instructions <https://docs.docker.com/>`_.

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

On each of your Flocker nodes, install the Flocker plugin:

.. prompt:: bash $

   apt-get install clusterhq-flocker-docker-plugin

The service can be started, stopped, or restarted using ``service``.
For example:

.. prompt:: bash $

   service flocker-docker-plugin restart

Testing Your Installation
=========================

Once installed, two simple Docker tests can be run to verify that the plugin is working correctly with the Flocker agents:

.. prompt:: bash $

   docker run -v apples:/data --volume-driver flocker busybox sh -c "echo hello > /data/file.txt"
   docker run -v apples:/data --volume-driver flocker busybox sh -c "cat /data/file.txt"

In this example, the first command uses the Flocker plugin for Docker as the volume driver to create a named volume called ``apples``.

In the second command we are reattaching the same volume from the first container, and verifying that the data (``hello``) has been preserved.

Upgrading the Plugin
====================

If you are upgrading from an earlier version of the plugin, make sure to stop the Docker daemon before doing so and then start it back up once the plugin has been upgraded.

Known Limitations
=================

* You should not move a volume from one node to another unless you are sure no containers are using the volume.

  The Flocker plugin will not stop volumes from being migrated out from underneath a running container.
  It is possible that Docker or your orchestration tool will prevent this from happening, but Flocker itself does not.
* ``--volumes-from`` and equivalent Docker API calls will only work if both containers are on the same machine.

  Some orchestration frameworks may not schedule containers in a way that respects this restriction, so check before using ``--volumes-from``.
* We recommend only using named volumes when using the Flocker plugin, i.e. volumes which are specified using the ``-v name:/path`` syntax in ``docker run``.

  Anonymous volumes can be created if you use a Docker image that specifies volumes and don't set a name for the volume, or if you add volumes in your Docker ``run`` commands without specified names (e.g. ``-v /path``).
  Docker defines volume drivers for the entire container, not per-volume, so the anonymous volumes will also be created by Flocker.
  As a result each time a container with an anonymous volume is started a new volume is created with a random name.
  This can waste resources when the underlying volumes are provisioned from, for example, EBS.
