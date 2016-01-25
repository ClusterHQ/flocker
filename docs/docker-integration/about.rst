.. _about-docker-integration:

============================
About the Docker Integration
============================

Flocker integrates with the Docker Engine, Docker Swarm and/or Docker Compose via the Flocker plugin for Docker.

The Flocker plugin for Docker is a Docker volumes plugin.

It allows you to control Flocker directly from the Docker CLI or a Docker Compose file.

It also works in multi-host environments where you're using Docker Swarm.

.. _concepts-docker-integration:

Concepts
========

Docker Volume
-------------

When a Docker volume is created with the ``flocker`` volume driver, either explicitly with ``docker volume create`` or implicitly by ``docker-compose up``, a Docker volume will get created on one or more Docker hosts.

You should think of these Docker volumes as **references** to Flocker volumes, which get created on-demand in Flocker.
That means that if you delete the Docker volume from one or more Docker hosts, the Flocker volume persists.
This is because Flocker volumes are persistent and live beyond the lifecycle of a Docker container, host or even Swarm.

.. TODO :ref:`flockerctl` to flockerctl page in Flocker Features

To delete a Flocker volume, use ``flockerctl``.

Flocker Volumes
---------------

Flocker volumes represent actual underlying storage, typically allocated from IaaS block device provider, such as EBS.
They have names, sizes, profiles and metadata.
