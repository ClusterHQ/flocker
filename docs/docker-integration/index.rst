.. _docker-integration:

======================
Docker, Swarm, Compose
======================

I suggest adding a paragraph here or removing the above heading all together, as two headings in a run looks quite untidy and also, somewhat defeats the point of having headings as separation. 


Flocker Installation Options
============================
.. raw:: html

	<div class="pods-eq">
	    <div class="pod-boxout pod-boxout--2up pod-boxout--recommended">
		   <img src="/_images/amazon-docker2x.png" alt="Amazon AWS logo"/>
		   <span>CloudFormation is the easiest way to get started on AWS.<em>Fastest</em></span>
		    <a href="cloudformation.html" class="button">Install</a>
	    </div>
	    <div class="pod-boxout pod-boxout--2up">
		    <img src="/_images/default2x.png" aria-hidden="true" alt=""/>
		   <span>Install Flocker manually to deploy it on infrastructure other than AWS.</span>
		    <a href="manual-install.html" class="button">Install manually</a>
	    </div>
	</div>

.. toctree::
   :hidden:

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

Other tutorials
---------------

* TODO: link to other tutorials on our blog

.. toctree::
   :hidden:

   tutorial-swarm-compose
   
Learn More
==========

To learn about the details of how this integration works, read :ref:`about-docker-integration`.

.. toctree::
   :hidden:

   about
   
.. What follows is a terrible hack to force sphinx to drag images into the build

.. raw:: html

   <div style="display:none;">

.. image:: /images/amazon-docker2x.png
.. image:: /images/default2x.png

.. raw:: html

   </div>
