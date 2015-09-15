
====================================
Installing the Flocker Docker Plugin
====================================

Before installing the Flocker Docker plugin, you will need to have installed Flocker on some nodes, using the instructions in the previous topics.

On the same machine where you ran ``flocker-ca`` while installing Flocker, you will need to generate a new API user certificate and key for a user named ``plugin``, as described in the :ref:`generate-api` instructions.

Upload these files to :file:`/etc/flocker/plugin.key` and :file:`/etc/flocker/plugin.crt` on the nodes where you want to run the Flocker Docker plugin.

You will also need to have Docker (at least version 1.8 or later) installed. The following command will install the latest version available:

.. prompt:: bash $

   wget -qO- https://get.docker.com/ | sudo sh

Now you can use the following instructions to install the Flocker Docker plugin on each of the nodes in your cluster.

On CentOS 7
===========

On each of your container agent servers, install the Flocker plugin:

.. prompt:: bash $

   yum install -y clusterhq-flocker-docker-plugin

The service can be started, stopped, or restarted using ``systemctl``.
For example:

.. prompt:: bash $

   systemctl restart flocker-docker-plugin
 

On Ubuntu 14.04
===============

On Ubuntu, it's best to ensure that Docker is using the ``AUFS`` storage driver.

The easiest way to do this is to add a ``-s aufs`` option to the :file:`/etc/default/docker` file.
For example::
   
   DOCKER_OPTS="-s aufs"

On each of your container agent servers, install the Flocker plugin:

.. prompt:: bash $

   apt-get install clusterhq-flocker-docker-plugin

The service can be started, stopped, or restarted using ``{[service flocker-docker-plugin restart}}``

Testing Your Installation
=========================

Once installed, two simple Docker tests can be run to verify that the plugin is working correctly with the Flocker agents:

.. prompt:: bash $

   docker run -v apples:/data --volume-driver flocker busybox sh -c "echo hello > /data/file.txt"
   docker run -v apples:/data --volume-driver flocker busybox sh -c "cat /data/file.txt"

The second command should print ``hello`` on the screen if everything has worked; the same data written to the Flocker volume in the first command.

Known limitations
=================

* If the volume exists on a different node and is currently being used by a container, the Flocker plugin does not stop it being migrated out from underneath the running container.
* If you use volumes in your Docker run commands without specified names, anonymous volumes can be created.
  This occurs as Docker defines volume drivers for the entire run command, not per-volume.
  If you do not want to create anonymous volumes, we recommend only using named volumes. 

