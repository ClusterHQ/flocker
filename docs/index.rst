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
    <div class="big-box orchestration recommended">
	    Docker, Swarm, Compose
		<img src="_images/docker.png" style="width:80px;"/>
		<br />
        <div style="position:relative; top:2em;">
        <a href="docker-integration/" class="button">Install</a>
        <em style="font-size:small;">easiest</em>
        </div>
    </div>
    <div class="big-box orchestration harder">
		Kubernetes
		<img src="_images/kubernetes.png" style="width:70px;"/>
        <br />
        <a href="kubernetes-integration/" class="button" style="position:relative; top: 2em">Install</a>
    </div>
    <div class="big-box orchestration harder">
		Mesos
		<img src="_images/mesos.png" style="width:70px;"/>
        <br />
        <a href="mesos-integration/" class="button" style="position:relative; top: 2em">Install</a>
    </div>
    <div class="big-box orchestration harder">
		Other
	 	<img src="_images/questionmark.png" style="width:80px;"/>
        <br />
        <a href="flocker-standalone/" class="button" style="position:relative; top: 2em">Install</a>
    </div>
    <div style="clear:both;"></div>

Is your favourite orchestration framework missing?
Let us know with the form below!

.. toctree::
   :maxdepth: 2

   supported
   docker-integration/index
   kubernetes-integration/index
   mesos-integration/index
   flocker-standalone/index
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

.. image:: images/docker.png
.. image:: images/kubernetes.png
.. image:: images/mesos.png
.. image:: images/questionmark.png

.. raw:: html

   </div>
