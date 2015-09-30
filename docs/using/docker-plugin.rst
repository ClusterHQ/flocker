.. _using-docker-plugin:

===================================
Using the Flocker Plugin for Docker
===================================

The Flocker plugin for Docker is a `Docker volumes plugin`_ connecting Docker on a host directly to Flocker, where Flocker agents will be running on the same host and hooked up to the Flocker control service.
Once :ref:`installed <install-docker-plugin>` it can be invoked by Docker using the :ref:`docker-plugin-cli` or :ref:`docker-plugin-api`.

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

.. _docker-plugin-cli:

Docker CLI
==========

A volume plugin makes use of the ``-v`` and ``--volume-driver`` flag on the docker run command.
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
