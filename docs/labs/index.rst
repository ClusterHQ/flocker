.. _labs-projects:

=============
Labs Projects
=============

This page lists some experimental projects which, by their nature, are developed to less rigorous quality and testing standards than the mainline Flocker distribution.

In other words, this is cool stuff that may or may not work.
It is not built with production-readiness in mind.

However, if you like one of these projects please let us know.
We intend to promote popular projects to be fully supported.

Flocker Docker plugin with CLI and GUI
--------------------------------------

By way of example, here is a 55 second demo of the :ref:`Flocker Docker plugin <docker-plugin>` provisioning portable Flocker volumes and moving them between hosts directly from the Docker CLI.

The video also shows our experimental :ref:`Volumes GUI <volumes-gui>` and :ref:`Volumes CLI <volumes-cli>` enabling you can see what's going on inside Flocker while this happens.

.. raw:: html

   <iframe width="100%" height="450" src="https://www.youtube.com/embed/OhWxJ_hOPx8?rel=0&amp;showinfo=0" frameborder="0" allowfullscreen style="margin-top:1em;"></iframe>

Goals of ClusterHQ Labs
-----------------------

Make it possible to:

* Integrate Flocker into other tools like :ref:`Swarm <labs-swarm>` and :ref:`Compose <labs-compose>`, via the :ref:`Flocker Docker plugin <labs-docker-plugin>`.
* See what's happening in your Flocker cluster with a :ref:`CLI <labs-volumes-cli>` and a :ref:`GUI <labs-volumes-gui>`.
* Make it easier to spin up a Flocker cluster in the first place with an :ref:`installer <labs-installer>`.
* Integrate Flocker with other popular tools, like :ref:`Weave <weave>`, :ref:`Mesosphere <labs-mesosphere>` and :ref:`Kubernetes <labs-kubernetes>`.

We believe that Flocker will be more successful if we focus on making it useful for managing data volumes *and* make it possible to be used as a tool which composes and integrates nicely with other components in the emerging new stack around Docker and containers.

Our biggest step towards this goal so far is the :ref:`Flocker Docker plugin <labs-docker-plugin>`, which makes Flocker pluggable directly into the Docker Engine and directly usable from the ``docker run`` CLI.

Also check out the `DockerCon Plugin Demos <https://plugin-demos-2015.github.io/>`_ site to see a joint project between ClusterHQ and Weaveworks.
This is the "ultimate integration demo" — a pre-built demo environment that includes Flocker, Weave, Swarm, Compose & Docker, all working together in harmony.

List of Labs projects
---------------------

.. toctree::
   docker-plugin
   installer
   volumes-cli
   volumes-gui
   swarm
   compose
   weave
   mesosphere
   kubernetes
