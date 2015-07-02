.. _labs-swarm:

==================
Flocker with Swarm
==================

With the :ref:`Flocker Docker plugin <labs-docker-plugin>`, and with Swarm support for the ``--volume-driver`` option, you can use Flocker together with Docker Swarm.

First, you need to :ref:`install Flocker <labs-installer>` and the :ref:`Flocker Docker plugin <labs-docker-plugin>`.
You can use our experimental  :ref:`Flocker Installer <labs-installer>` to do this.

Then, you need a version of Swarm that supports Flocker volumes.

We have compiled a swarm binary for you and `uploaded it here <http://storage.googleapis.com/experiments-clusterhq/docker-binaries/swarm-volume-driver>`_.

You can use the following commands to install swarm from our uploaded binary.

.. prompt:: bash $

    sudo wget -O /usr/bin/swarm http://storage.googleapis.com/experiments-clusterhq/docker-binaries/swarm-volume-driver

Alternatively - you can `compile swarm from master <https://github.com/docker/swarm#development-installation>`_ and the resulting binary will also have ``--volume-driver`` support.

Running a container via swarm
=============================

Here is an example of a docker run command that provisions a Flocker volume via Swarm.

.. prompt:: bash $

    # first - point our Docker client at the Swarm daemon
    export DOCKER_HOST=tcp://localhost:2378
    # now run a container with a Flocker volume
    docker run -v demo:/data --volume-driver flocker redis


Targeting specific hosts
========================

You can use Swarm constraints to target containers to specific hosts.
Here is an example of a Docker run command that will target the Redis container onto ``host1``.

.. prompt:: bash $

    docker run \
        -v demo:/data \
        --volume-driver flocker \
        -e constraint:node==host1 \
        redis

Then, if we wanted to migrate the Redis container onto ``host2`` - we would use a different constraint:

.. prompt:: bash $

    docker run \
        -v demo:/data \
        --volume-driver flocker \
        -e constraint:node==host2 \
        redis

In this scenario, Flocker will migrate the data from host1 to host2.

Demo
====

Also check out the `DockerCon Plugin Demos <https://plugins-demo-2015.github.io/>`_ site to see a joint project between ClusterHQ and Weaveworks.
This is the "ultimate integration demo" — a pre-built demo environment that includes Flocker, Weave, Swarm, Compose & Docker, all working together in harmony.
