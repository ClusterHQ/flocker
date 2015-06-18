.. _labs-docker-plugin:

=====================
Flocker Docker plugin
=====================

The Flocker Docker plugin is a `Docker volumes plugin <https://github.com/docker/docker/blob/master/experimental/plugins_volume.md>`_, connecting Docker on a host directly to Flocker, which must have an agent running on the same host.

As a user of Docker, it means you can use Flocker directly via:

* The ``docker run -v name:path --volume-driver=flocker`` syntax.
* The ``VolumeDriver`` parameter on ``/containers/create`` in the Docker Remote API.

See the `Docker documentation on volume plugins <https://github.com/docker/docker/blob/master/experimental/plugins_volume.md>`_.

See also the `GitHub repo for this project <https://github.com/ClusterHQ/flocker-docker-plugin>`_.

How it works
============

The Flocker Docker plugin operates on the ``name`` passed to Docker in the ``docker run`` command and associates it with a Flocker dataset with the same name (i.e. with metadata ``name=foo``).

There are three main cases:

* If the volume does not exist at all on the Flocker cluster, it is created on the host which requested it.
* If the volume exists on a different host, it is moved in-place before the container is started.
* If the volume exists on the current host, the container can be started straight away.

Multiple containers can use the same Flocker volume (by referencing the same volume name, or by using Docker's ``--volumes-from``) so long as they are running on the same host.

Quickstart installation
=======================

You can use the ``flocker-plugin`` tool which is part of the :ref:`installer <labs-installer>` to quickly install the Flocker Docker Plugin on a cluster you set up with that tool.

Otherwise, if you want to install the Flocker Docker plugin manually, you can follow the following instructions.

Manual Installation on Ubuntu 14.04
===================================

First :ref:`install Flocker <labs-installer>`.

Install the experimental build of Docker:

.. prompt:: bash $

    wget -qO- https://experimental.docker.com/ | sudo sh

On each of your container agent servers, install the Flocker plugin:

.. prompt:: bash $

    sudo apt-get install -y python-pip python-dev
    sudo pip install git+https://github.com/clusterhq/flocker-docker-plugin.git

We need to define some configuration which will make it into the environment of the plugin:

.. prompt:: bash $

    FLOCKER_CONTROL_SERVICE_BASE_URL=https://your-control-service:4523/v1
    MY_NETWORK_IDENTITY=1.2.3.4

Replace ``your-control-service`` with the hostname of the control service you specified when you created your cluster.
Replace ``1.2.3.4`` with the IP address of the host you are installing on (if your public and private IPs differ, it is generally best to use the *private* IP address of your hosts).

Write out up an upstart script to automatically start the Flocker plugin on boot:

.. prompt:: bash $

    cat <<EOF > /etc/init/flocker-docker-plugin.conf
    # flocker-docker-plugin - flocker-docker-plugin job file
    description "Flocker Plugin service"
    author "ClusterHQ <support@clusterhq.com>"
    respawn
    env FLOCKER_CONTROL_SERVICE_BASE_URL=${FLOCKER_CONTROL_SERVICE_BASE_URL}
    env MY_NETWORK_IDENTITY=${MY_NETWORK_IDENTITY}
    exec flocker-docker-plugin
    EOF
    service flocker-docker-plugin restart

Known limitations
=================

If the volume exists on a different host and is currently being used by a container, the Flocker plugin does not stop it being migrated out from underneath the running container.
