.. _mesos-integration:

=====
Mesos
=====

.. raw:: html

    <div class="admonition labs">
        <p>This page describes one of our experimental projects, developed to less rigorous quality and testing standards than the mainline Flocker distribution. It is not built with production-readiness in mind.</p>
	</div>

Flocker works with Mesos via two different integration paths:

* Using the Mesos-Flocker Isolator to provide storage to any Mesos framework and any application, whether Dockerized or not.
  Currently experimental.
* Using Marathon and the Flocker plugin for Docker to provide storage to Dockerized applications running on Marathon.
  See our `blog post below <https://clusterhq.com/2015/10/06/marathon-ha-demo/>`_ for details.

.. raw:: html

    <div class="pods-eq">
	    <div class="pod-boxout pod-boxout--tutorial pod-boxout--2up">
		   <span>Using the Mesos-Flocker Isolator</span>
		     <a href="http://flocker.mesosframeworks.com/" class="button" target="_blank">Launch the Mesos-Flocker Isolator</a>
	    </div>
	    <div class="pod-boxout pod-boxout--tutorial pod-boxout--2up">
		   <span>View the Mesos-Flocker isolator on GitHub</span>
		     <a href="https://github.com/ClusterHQ/mesos-module-flocker" class="button" target="_blank">Open the GitHub repo</a>
	    </div>
	</div>

.. _mesos-tutorials:

.. XXX this section should be returned when there are tutorials

Related Blog Articles
=====================

* `Demo: High Availability with Marathon and Flocker <https://clusterhq.com/2015/10/06/marathon-ha-demo/>`_
