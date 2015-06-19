.. _labs-projects:

=============
Labs Projects
=============

This page lists some experimental projects which, by their nature, are developed to less rigorous quality and testing standards than the mainline Flocker distribution.

In other words, this is cool stuff that may or may not work.
It is not built with production-readiness in mind.

However, if you like one of these projects please :ref:`let us know <labs-contact>`.

If we get lots of positive feedback about any one of these projects then we will consider it for the main Flocker roadmap.

.. _labs-demo:

Flocker Docker plugin with CLI and GUI
======================================

By way of example, here is a 55 second demo of the :ref:`Flocker Docker plugin <labs-docker-plugin>` provisioning portable Flocker volumes and moving them between hosts directly from the Docker CLI.

The video also shows our experimental :ref:`Volumes GUI <labs-volumes-gui>` and :ref:`Volumes CLI <labs-volumes-cli>` which both give insight into what Flocker is doing while this happens.

.. raw:: html

   <iframe width="100%" height="450" src="https://www.youtube.com/embed/OhWxJ_hOPx8?rel=0&amp;showinfo=0" frameborder="0" allowfullscreen style="margin-top:1em;"></iframe>

Goals of ClusterHQ Labs
=======================

Currently Flocker supports both volume-centric operation via the dataset API and container-centric operation via the container API and the ``flocker-deploy`` tooling.

The goals of ClusterHQ Labs are to make it possible to:

* Integrate Flocker with tools like :ref:`Swarm <labs-swarm>` and :ref:`Compose <labs-compose>`, via the :ref:`Flocker Docker plugin <labs-docker-plugin>`.
* See what's happening in your Flocker cluster with a :ref:`CLI <labs-volumes-cli>` and a :ref:`GUI <labs-volumes-gui>`.
* Make it easier to spin up a Flocker cluster in the first place with an :ref:`installer <labs-installer>`.
* Integrate Flocker with other popular tools, like :ref:`Weave <labs-weave>`, :ref:`Mesosphere <labs-mesosphere>` and eventually :ref:`Kubernetes <labs-kubernetes>`.

**We believe that Flocker will be more successful if, as well as focusing on making it useful for managing data volumes, we work on integrating it with other components in the emerging Docker and container ecosystem.**

Our biggest step towards this goal so far is the :ref:`Flocker Docker plugin <labs-docker-plugin>`, which makes Flocker pluggable directly into the Docker Engine and directly usable from the ``docker run`` CLI.

Mega demo
=========

Also check out the `DockerCon Plugin Demos <https://plugins-demo-2015.github.io/>`_ site to see a joint project between ClusterHQ and Weaveworks.
This is the "ultimate integration demo" — a pre-built demo environment that includes Flocker, Weave, Swarm, Compose & Docker, all working together in harmony.

.. _labs-contact:

Getting in touch with ClusterHQ Labs
====================================

Come and talk to us on our IRC channel which is on Freenode ``#clusterhq``.

Or, file an issue on GitHub for the respective project:

* `Flocker Docker plugin <https://github.com/clusterhq/flocker-docker-plugin>`_ for integration-related issues.
* `Unofficial Flocker Tools <https://github.com/clusterhq/unofficial-flocker-tools>`_ for CLI, GUI, or installer issues.

List of Labs projects
=====================

.. toctree::
   :maxdepth: 1

   docker-plugin
   installer
   volumes-cli
   volumes-gui
   swarm
   compose
   weave
   mesosphere
   kubernetes
