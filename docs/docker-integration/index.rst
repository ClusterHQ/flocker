.. _docker-integration:

======================
Docker, Swarm, Compose
======================

Flocker works with Docker, Swarm and/or Compose via the Flocker Plugin for Docker.
Follow an installation guide to get started:

Flocker Installation Options
============================
.. raw:: html

	<div class="pods-eq">
	    <div class="pod-boxout pod-boxout--2up pod-boxout--recommended">
		   <img src="../_images/amazon-docker2x.png" alt="Amazon AWS logo"/>
		   <span>Use our CloudFormation template to install Flocker on AWS<em>Fastest</em></span>
		   <a href="cloudformation.html" class="button button--fast">Install</a>
	    </div>
	    <div class="pod-boxout pod-boxout--2up">
		   <img src="../_images/default2x.png" aria-hidden="true" alt=""/>
		   <span>Install Flocker and Docker Swarm manually<em><a href="../supported/index.html">Works with all Supported Configurations</a></em></span>
		   <a href="manual-install.html" class="button">Install Manually</a>
	    </div>
	</div>

.. the following causes the toctree to be hidden on page but not in the navigation, meaning that when on the linked page, the navigation shows you where you are, which is crucial for UX.

.. raw:: html

   <style>
   .toctree-wrapper { display: none; }
   </style>

.. toctree::

   cloudformation
   manual-install

.. _docker-tutorials:

Follow a Tutorial
=================

.. raw:: html

    <div class="pods-eq">
	    <div class="pod-boxout pod-boxout--2up pod-boxout--tutorial">
		   <span>Tutorial: using Flocker with Docker Swarm and Compose</span>
		    <a href="tutorial-swarm-compose.html" class="button">Follow Tutorial</a>
	    </div>
    </div>

Related Blog Articles
=====================

* `Tutorial: PostgreSQL on Docker with Flocker <https://clusterhq.com/2016/01/08/tutorial-flocker-volume-driver-postgres/>`_
* `Walkthrough: Docker Volumes vs Docker Volumes with Flocker <https://clusterhq.com/2015/12/09/difference-docker-volumes-flocker-volumes/>`_
* `Deploying and migrating an Elasticsearch-Logstash-Kibana stack using Docker Part 1 <https://clusterhq.com/2016/01/12/a-single-node-elk-flocker/>`_
* `Deploying and migrating an Elasticsearch-Logstash-Kibana stack using Docker Part 2 <https://clusterhq.com/2016/01/12/b-multinode-elk-flocker/>`_

.. toctree::
   :hidden:

   tutorial-swarm-compose
   
Learn More
==========

To learn more about this integration, see the following topics:

* :ref:`about-docker-integration`
* :ref:`using-docker-plugin`

.. toctree::
   :hidden:

   about
   control-plugin
   
.. What follows is a terrible hack to force sphinx to drag images into the build

.. raw:: html

   <div style="display:none;">

.. image:: /images/amazon-docker2x.png
.. image:: /images/default2x.png

.. raw:: html

   </div>
