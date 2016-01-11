.. raw:: html

    <style>
        .toctree-wrapper { display:none; }
    </style>

==================
Installing Flocker
==================

.. _supported-orchestration-frameworks:

.. raw:: html

    <p>To install Flocker, you first need to choose which stack you using.</p>
    <p>Flocker adds support for stateful containers to a range of container orchestration frameworks.</p>

	<!-- This too needs to become Sphinx directives, rather than raw HTML. -->
	<div class="pods-eq">
	    <div class="pod-boxout pod-boxout--orchestration pod-boxout--recommended">
			<img src="_images/docker2x.png" alt="Docker logo"/>
			<span>Docker, Swarm, Compose <em>Fastest</em></span>
	        <a href="docker-integration/" class="button button--fast">Install</a>
	    </div>
	    
	    <div class="pod-boxout pod-boxout--orchestration">
			<img src="_images/kubernetes2x.png" alt="Kubernetes logo"/>
			<span>Kubernetes</span>
	        <a href="kubernetes-integration/" class="button">Install</a>
	    </div>
	    
	    <div class="pod-boxout pod-boxout--orchestration">
			<img src="_images/mesos2x.png" alt="mesos logo"/>
			<span>Mesos</span>
	        <a href="mesos-integration/" class="button">Install</a>
	    </div>
	</div>
	
	 <div class="pod-boxout pod-boxout--minor pod-boxout--orchestration">
		<span><img src="_images/icon-question2x.png" aria-hidden="true" alt=""/>&nbsp;Install using something else</span>
        <a href="flocker-standalone/" class="button">Install</a>
    </div>

Is your favourite orchestration framework missing?
Let us know with the form below!

.. toctree::
   :maxdepth: 2

   docker-integration/index
   kubernetes-integration/index
   mesos-integration/index
   flocker-standalone/index
   supported
   flocker-features/index
   reference/index
   labs/index
   releasenotes/index
   faq/index
   gettinginvolved/index

.. The version page is used only for a version of the documentation to know what the latest version is.

.. toctree::
   :hidden:

   version
   installation/index

.. What follows is a terrible hack to force sphinx to drag images into the build

.. raw:: html

   <div style="display:none;">

.. image:: images/docker2x.png
.. image:: images/kubernetes2x.png
.. image:: images/mesos2x.png
.. image:: images/icon-question2x.png

.. raw:: html

   </div>
