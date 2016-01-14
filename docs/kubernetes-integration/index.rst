.. _kubernetes-integration:

==========
Kubernetes
==========

Flocker works with Kubernetes 1.1 or later via the built-in Flocker driver for Kubernetes.

Flocker Installation Options
============================

.. raw:: html

    <div class="pods-eq">
	    <div class="pod-boxout pod-boxout--short pod-boxout--2up">
		   <img src="/_images/kubernetes2x.png" alt="Kubernetes logo"/>
		   <span>Install Flocker manually</span>
		   <a href="manual-install.html" class="button">Install</a>
	    </div>
	</div>

.. the following causes the toctree to be hidden on page but not in the navigation, meaning that when on the linked page, the navigation shows you where you are, which is crucial for UX.

.. raw:: html

   <style>
   .toctree-wrapper { display: none; }
   </style>

.. toctree::

   manual-install

.. _kubernetes-tutorials:

Follow a Tutorial
=================

.. raw:: html

    <div class="pods-eq">
	    <div class="pod-boxout pod-boxout--2up pod-boxout--tutorial">
		   <span>Tutorial: using Flocker with Kubernetes</span>
		     <a href="tutorial-kubernetes.html" class="button">Follow Tutorial</a>
	    </div>
	</div>

Learn more on our blog
----------------------

* `Demo: High Availability with Kubernetes and Flocker <https://clusterhq.com/2015/12/22/ha-demo-kubernetes-flocker/>`_

.. toctree::
   :hidden:

   tutorial-kubernetes

Learn More
==========

To learn about the details of how this integration works, read :ref:`about-kubernetes-integration`.

.. toctree::
   :hidden:

   about
   
.. What follows is a terrible hack to force sphinx to drag images into the build

.. raw:: html

   <div style="display:none;">

.. image:: /images/kubernetes2x.png

.. raw:: html

   </div>
