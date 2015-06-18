=============
Labs Projects
=============

This page lists some experimental projects which, by their nature, are developed to less rigorous quality and testing standards than the mainline Flocker distribution.

In other words, this is cool stuff that may or may not work.
It is not built with production-readiness in mind.

However, if you like one of these projects please let us know.
We intend to promote popular projects to be fully supported.

Demo
====

Here is a 55 second demo of the Flocker Docker plugin provisioning portable Flocker volumes and moving them between hosts directly from the Docker CLI.
The video also shows the experimental GUI and CLI so you can see what's going on inside Flocker while this happens.

.. raw:: html

   <iframe width="100%" height="450" src="https://www.youtube.com/embed/OhWxJ_hOPx8?rel=0&amp;showinfo=0" frameborder="0" allowfullscreen></iframe>

Goals of ClusterHQ Labs
=======================

Make it possible to:

* Integrate Flocker into other tools like Swarm and Compose, via the Flocker Docker plugin.
* See what's happening in your Flocker cluster (CLI/GUI).
* Make it easy to spin up a Flocker cluster in the first place (installer).
* Integrate Flocker with other popular tools, like Weave, Mesosphere and Kubernetes.

We believe that Flocker will be more successful if we focus on making it great at dealing with data *and* make it possible to be used as a tool which composes and integrates nicely with other components in the emerging new stack around Docker and containers.

Our biggest step towards this goal so far is the Flocker Docker plugin, which makes Flocker pluggable directly into the Docker Engine and directly usable from the ``docker run`` CLI.

Also check out the `DockerCon Plugin Demos landing page <https://plugin-demos-2015.github.io/>`_ to see a joint project between ClusterHQ and Weaveworks.
This is the "ultimate integration demo" — a pre-built demo environment that includes Flocker, Weave, Swarm, Compose & Docker, all working in harmony.

.. toctree::
   docker-plugin
   installer
   volumes-cli
   volumes-gui
   weave
   swarm
   compose
   mesosphere
   kubernetes
