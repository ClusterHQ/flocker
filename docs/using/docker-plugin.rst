.. _using-docker-plugin:

===================================
Using The Flocker Plugin for Docker
===================================

The Flocker plugin for Docker is a `Docker volumes plugin`_ connecting Docker on a host directly to Flocker, where Flocker agents will be running on the same host and hooked up to the Flocker control service.
Once :ref:`installed <install-docker-plugin>` it can be invoked by Docker using the Docker CLI or Docker Remote API.

.. include:: ../using/docker-plugin-limitations.rst

Docker CLI
==========

A volume plugin makes use of the `-v` and `--volume-driver` flag on the docker run command.
The `-v` flag accepts a volume name and the `--volume-driver` flag a driver type.
The Flocker driver type is `flocker`.

.. prompt:: bash $

   docker run -ti -v volumename:/data --volume-driver=*flocker* busybox sh

In this example, a Flocker volume with name of `volumename` is created.
If a container is started with a volume of the same name in your Flocker cluster, the volume will be migrated to the calling node before Docker starts the container.

.. _`Docker volumes plugin`: https://github.com/docker/docker/blob/master/docs/extend/plugins_volume.md

