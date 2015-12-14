.. _docker-plugin:

=============================
The Flocker Plugin for Docker
=============================

The Flocker plugin for Docker allows Flocker to manage your data volumes while using other tools such as Docker, Docker Swarm, or Mesos to manage your containers.
The Flocker plugin for Docker is a `Docker volumes plugin`_, connecting Docker on a host directly to Flocker, where Flocker agents will be running on the same host and hooked up to the Flocker control service.

.. XXX FLOC 3156 will add an architecture diagram to this document.

In contrast to the normal :ref:`Flocker container-centric architecture <flocker-containers-architecture>`, when using the Flocker plugin for Docker the Flocker volume manager (control service + dataset agents) is **being controlled by Docker**, rather than the Flocker container manager controlling Docker.
This allows for easier integration with other Docker ecosystem tools.

Also, please note that :ref:`Docker Swarm <labs-swarm>` and Flocker must be configured on the **same set of nodes**.

As a user of Docker, it means you can use Flocker directly via:

* The ``docker run -v name:path --volume-driver=flocker`` syntax.
* The ``VolumeDriver`` parameter on ``/containers/create`` in the Docker Remote API (set it to ``flocker``).

For more information, see the :ref:`using-docker-plugin` documentation, and the `Docker documentation on volume plugins`_.

The Flocker plugin for Docker depends on Docker 1.8 or later.

.. note::
    Note that you should either use the Flocker plugin for Docker to associate containers with volumes (the integration architecture described above), or you should use the :ref:`Flocker containers API <api>` and :ref:`flocker-deploy CLI <cli>`, but not both.

    They are distinct architectures.
    The integration approach allows Docker to control Flocker via the Flocker Dataset API.
    This allows Flocker to be used in conjunction with other ecosystem tools like :ref:`Docker Swarm <labs-swarm>` and :ref:`Docker Compose <labs-compose>`.

.. _`Docker volumes plugin`: https://github.com/docker/docker/blob/master/docs/extend/plugins_volume.md
.. _`Docker documentation on volume plugins`: `Docker volumes plugin`_

How It Works
============

.. begin-body

The Flocker plugin for Docker enables you to run containers with named volumes without worrying which server your data is on.

The plugin will create or move the volumes in place as necessary.

The Flocker plugin for Docker operates on the ``name`` passed to Docker in the ``docker run`` command and associates it with a Flocker dataset with the same name (i.e. with metadata ``name=foo``).

There are three main cases which the plugin handles:

* If the volume does not exist at all on the Flocker cluster, it is created on the host which requested it.
* If the volume exists on a different host, it is moved in-place before the container is started.
* If the volume exists on the current host, the container is started straight away.

Multiple containers can use the same Flocker volume (by referencing the same volume name, or by using Docker's ``--volumes-from``) so long as they are running on the same host.

.. end-body

Demo
====

This demo shows both the Flocker plugin for Docker in conjunction with the :ref:`Volumes CLI <labs-volumes-cli>` and :ref:`Volumes GUI <labs-volumes-gui>`.

.. raw:: html

   <iframe width="100%" height="450" src="https://www.youtube.com/embed/OhWxJ_hOPx8?rel=0&amp;showinfo=0" frameborder="0" allowfullscreen style="margin-top:1em;"></iframe>

Also check out the `DockerCon Plugin Demos <https://plugins-demo-2015.github.io/>`_ site to see a joint project between ClusterHQ and Weaveworks.
This is the "ultimate integration demo", a pre-built demo environment that includes Flocker, Weave, Swarm, Compose, and Docker, all working together in harmony.

Flocker also has planned integrations with major orchestration tools such as Docker Swarm, Kubernetes and Apache Mesos.
More information on these integrations is :ref:`available in the Labs section <labs-projects>`.

Get Started with the Flocker Plugin for Docker
==============================================

The plugin is installed on each node in your cluster, and can be installed at the same time as the Flocker node services.
For more information, see :ref:`installing-flocker-node`.

When the plugin has been installed, you will need to :ref:`create API client certificates for access to the Flocker REST API <generate-api-docker-plugin>`, and then :ref:`enable the plugin <enabling-agent-service>` before you can use it to :ref:`control Flocker <using-docker-plugin>`.
