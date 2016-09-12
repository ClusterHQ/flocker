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
		   <img src="../_static/images/kubernetes2x.png" alt="Kubernetes logo"/>
		   <span>Install Flocker manually
           <em><a href="../supported/index.html">Works with all Supported Configurations</a></em></span>
		   <a href="manual-install.html" class="button">Install</a>
	    </div>
	</div>

.. the following causes the toctree to be hidden on page but not in the navigation, meaning that when on the linked page, the navigation shows you where you are, which is crucial for UX.

.. raw:: html

   <style>
   .toctree-wrapper { display: none; }
   </style>

.. toctree::

   about
   manual-install

.. _kubernetes-tutorials:

Tutorial
========

.. XXX this title should be renamed to "Tutorials" when there are more than one tutorial

.. raw:: html

    <div class="pods-eq">
	    <div class="pod-boxout pod-boxout--2up pod-boxout--tutorial">
		   <span>Tutorial: Using Flocker volumes, provided by Kubernetes</span>
		     <a href="http://kubernetes.io/docs/user-guide/volumes/#flocker" target="_blank" class="button">Open the Kubernetes Tutorial</a>
	    </div>
	</div>

Related Blog Articles
=====================

* `Demo: High Availability with Kubernetes and Flocker <https://clusterhq.com/2015/12/22/ha-demo-kubernetes-flocker/>`_

Learn More
==========

To learn about the details of how this integration works, read :ref:`about-kubernetes-integration`.

.. toctree::
   :hidden:

   about
