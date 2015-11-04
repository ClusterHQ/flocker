.. _install-docker-plugin:

========================================
Installing the Flocker Plugin for Docker
========================================

:ref:`docker-plugin` allows Flocker to manage your data volumes while using other tools such as Docker, Docker Swarm, or Mesos to manage your containers.

Before installing the Flocker plugin for Docker, you will need to have installed Flocker on some nodes, using the :ref:`node installation instructions <installing-flocker-node>`.

The Flocker plugin for Docker requires access to the Flocker REST API.
To use the plugin, you will need to create an API user certificate and key for a user named ``plugin`` on each node. 
For more information, see the :ref:`generate-api` instructions.

For example, you can use the ``flocker-ca`` command as below:

.. prompt:: bash $

   flocker-ca create-api-certificate plugin
   scp ./plugin.crt root@172.16.255.251:/etc/flocker/plugin.crt
   scp ./plugin.key root@172.16.255.251:/etc/flocker/plugin.key

Upload the :file:`plugin.key` and :file:`plugin.crt` file to the  :file:`/etc/flocker/` folder on the nodes where you want to run the Flocker plugin for Docker.

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

   apt-get install -y clusterhq-flocker-docker-plugin

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

.. include:: plugin-restrictions.rst
