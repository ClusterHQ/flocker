.. _mesos-integration:

=====
Mesos
=====

Flocker works with Mesos via two different integration paths.

* With Marathon and Flocker Plugin for Docker to provide storage to Dockerized applications running on Marathon.
  `See our blog post for details <https://clusterhq.com/2015/10/06/marathon-ha-demo/>`_.
* With the `Mesos-Flocker Isolator <http://flocker.mesosframeworks.com/>`_ to provide storage to any Mesos framework and any application, whether Dockerized or not.
  Currently experimental.

.. raw:: html

   <style>
   .toctree-wrapper { display: none; }
   </style>

.. _mesos-tutorials:

Follow a Tutorial
=================

.. raw:: html

    <div class="pods-eq">
	    <div class="pod-boxout pod-boxout--tutorial pod-boxout--2up">
		   <span>Using Mesos isolator for Flocker</span>
		     <a href="https://github.com/ClusterHQ/mesos-module-flocker" class="button" target="_blank">GitHub Repo</a>
	    </div>
	</div>

Learn more on our blog
----------------------

* `Demo: High Availability with Marathon and Flocker <https://clusterhq.com/2015/10/06/marathon-ha-demo/>`_

Learn More
==========

To learn about the details of how these integrations work, read :ref:`about-mesos-integration`.

.. toctree::
   :hidden:

   about
