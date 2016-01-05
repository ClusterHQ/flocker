.. raw:: html

    <!-- This toctree-wrapper and next button override is obviously a horrible
         hack, and we need a better way of disabling the toctree on the front
         page. -->
    <style>
        .toctree-wrapper { display:none; }
        a.button.rel { display:none; }
        h1 { display:none; }
        .big-box {
            border:2px solid #777;
            width:11em;
            height:11em;
            float:left;
            margin:0.5em;
            padding:0.5em;
            margin-top:20px; margin-bottom:20px;
        }
        .orchestration {
            border-color: #80B164;
        }
    </style>

==================
Installing Flocker
==================

.. _supported-orchestration-frameworks:

.. raw:: html

    <h2>Which stack are you using?</h2>
    <p>Flocker adds support for stateful containers to a range of container orchestration frameworks.</p>

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="big-box orchestration">
	    Docker, Swarm, Compose
		<img src="_images/docker.png" style="width:80px;"/>
		<br />
        <a href="docker-integration/" class="button" style="position:relative; top: 2em">Install</a>
    </div>
    <div class="big-box orchestration">
		Kubernetes
		<img src="_images/kubernetes.png" style="width:70px;"/>
        <br />
        <a href="kubernetes-integration/" class="button" style="position:relative; top: 2em">Install</a>
    </div>
    <div class="big-box orchestration">
		Mesos
		<img src="_images/mesos.png" style="width:70px;"/>
        <br />
        <a href="mesos-integration/" class="button" style="position:relative; top: 2em">Install</a>
    </div>
    <div class="big-box orchestration">
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
