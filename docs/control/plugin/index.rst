.. _using-docker-plugin:

======================================================
Controlling Flocker with the Flocker Plugin for Docker
======================================================

The Flocker plugin for Docker is a `Docker volumes plugin`_ connecting Docker on a host directly to Flocker, where Flocker agents will be running on the same host and hooked up to the Flocker control service.

The following instructions describe how to control Flocker by using the :ref:`docker-plugin-cli` or :ref:`docker-plugin-api`. This can only be done once you have :ref:`installed the Flocker plugin for Docker <install-docker-plugin>`.

.. include:: ../../install/plugin-restrictions.rst

.. _docker-plugin-cli:

Docker CLI
==========

A volume plugin makes use of the ``-v`` and ``--volume-driver`` flags on the docker ``run`` command.
The ``-v`` flag accepts a volume name and the ``--volume-driver`` flag a driver type.
The Flocker driver type is ``flocker``.

.. prompt:: bash $

   docker run -ti -v volumename:/data --volume-driver=flocker busybox sh

In this example, a Flocker volume with name of ``volumename`` is created.
If a container is started with a volume of the same name in your Flocker cluster, the volume will be migrated to the calling node before Docker starts the container.

.. _docker-plugin-api:

Docker Remote API
=================

The Docker Remote API call which supports ``--volume-driver`` in the CLI is undocumented at time of writing.
However, currently is it is specified by the ``VolumeDriver`` attribute of ``HostConfig`` under ``POST /containers/create``.
Set the container ``Mount`` attributes according to the instructions in the :ref:`docker-plugin-cli` section.
Full documentation for ``VolumeDriver`` will appear after the release of `Docker Engine 1.9`_.

.. _`Docker volumes plugin`: https://docs.docker.com/extend/plugins_volume/
.. _`Docker Engine 1.9`: https://github.com/docker/docker/wiki/Engine-1.9.0