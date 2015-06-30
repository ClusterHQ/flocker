.. _labs-weave:

==================
Flocker with Weave
==================

Flocker gives you portable volumes.
Weave gives you portable cross-host network identity.

This provides appropriate multi-host abstractions so that stateful containers can be more easily moved (migrated) between physical hosts.

Installation
============

Flocker and Weave both have Docker plugins.
So you can simply install the :ref:`Flocker Docker plugin <labs-docker-plugin>` and install the `Weave Docker plugin <http://weave.works/docker-plugins/index.html>`_ and it should Just Work.

Demo
====

Also check out the `DockerCon Plugin Demos <https://plugins-demo-2015.github.io/>`_ site to see a joint project between ClusterHQ and Weaveworks.
This is the "ultimate integration demo" — a pre-built demo environment that includes Flocker, Weave, Swarm, Compose & Docker, all working together in harmony.
