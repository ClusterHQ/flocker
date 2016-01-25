.. _mesos-integration:

=====
Mesos
=====

.. raw:: html

    <div class="admonition labs">
        <p>This page describes one of our experimental projects, developed to less rigorous quality and testing standards than the mainline Flocker distribution. It is not built with production-readiness in mind.</p>
	</div>

Flocker works with Mesos via two different integration paths.

* With the `Mesos-Flocker Isolator <http://flocker.mesosframeworks.com/>`_ to provide storage to any Mesos framework and any application, whether Dockerized or not.
  Currently experimental.
* With Marathon and the Flocker plugin for Docker to provide storage to Dockerized applications running on Marathon.
  `See our blog post for details <https://clusterhq.com/2015/10/06/marathon-ha-demo/>`_.

.. _mesos-tutorials:

Follow a Tutorial
=================

.. raw:: html

    <div class="pods-eq">
	    <div class="pod-boxout pod-boxout--tutorial pod-boxout--2up">
		   <span>Using Mesos isolator for Flocker</span>
		     <a href="https://github.com/ClusterHQ/mesos-module-flocker" class="button" target="_blank">GitHub Readme</a>
	    </div>
	</div>

Related Blog Articles
=====================

* `Demo: High Availability with Marathon and Flocker <https://clusterhq.com/2015/10/06/marathon-ha-demo/>`_
