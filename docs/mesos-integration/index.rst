.. _mesos-integration:

=====
Mesos
=====

Flocker works with Mesos via two different integration paths:

* With Marathon and Flocker Plugin for Docker to provide storage to Dockerized applications running on Marathon.
* With the `Mesos-Flocker Isolator <http://flocker.mesosframeworks.com/>`_ to provide storage to any Mesos framework or application.

Flocker Installation Options
============================

.. raw:: html

    <div class="pods-eq">
	    <div class="pod-boxout pod-boxout--short pod-boxout--2up">
		   <img src="/_images/mesos2x.png" alt="Mesos logo"/>
		   <span>Install Flocker manually</span>
		   <a href="manual-install.html" class="button">Install</a>
	    </div>
	</div>

.. toctree::
   :hidden:

   manual-install

.. _mesos-tutorials:

Follow a Tutorial
=================

.. raw:: html

     <div class="pods-solo">
	    <div class="pod-boxout pod-boxout--tutorial">
		   <span>Tutorial: using Flocker with Mesos</span>
		     <a href="tutorial-mesos.html" class="button">Follow Tutorial</a>
	    </div>
	</div>

Learn more on our blog
----------------------

* `Demo: High Availability with Marathon and Flocker <https://clusterhq.com/2015/10/06/marathon-ha-demo/>`_

.. toctree::
   :hidden:

   tutorial-mesos


Learn More
==========

To learn about the details of how this integration works, read :ref:`about-mesos-integration`.

.. toctree::
   :hidden:

   about
