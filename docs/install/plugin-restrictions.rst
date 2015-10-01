Known Limitations
=================

* You should not move a volume from one node to another unless you are sure no containers are using the volume.

  The plugin will not stop volumes from being migrated out from underneath a running container.
  It is possible that Docker or your orchestration tool will prevent this from happening, but Flocker itself does not.
* ``--volumes-from`` and equivalent Docker API calls will only work if both containers are on the same machine.

  Some orchestration frameworks may not schedule containers in a way that respects this restriction, so check before using ``--volumes-from``.
* We recommend that when using the Flocker plugin for Docker that you only use named volumes (volumes which are specified using the ``-v name:/path`` syntax in ``docker run``).

  Anonymous volumes can be created if you use a Docker image that specifies volumes and don't set a name for the volume, or if you add volumes in your Docker ``run`` commands without specified names (for example, ``-v /path``).
  Docker defines volume drivers for the entire container, not per-volume, so the anonymous volumes will also be created by Flocker.
  As a result each time a container with an anonymous volume is started a new volume is created with a random name.
  This can waste resources when the underlying volumes are provisioned from, for example, EBS.
