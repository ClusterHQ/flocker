.. raw:: html

    <!-- This toctree-wrapper and next button override is obviously a horrible
         hack, and we need a better way of disabling the toctree on the front
         page. -->
    <style>
        .toctree-wrapper { display:none; }
        a.button.rel { display:none; }
        .big-box {
            border:1px solid black;
            width:10em;
            height:10em;
            float:left;
            margin:0.5em;
        }
        .small-box {
            border:1px solid black;
            width:7em;
            height:7em;
            float:left;
            margin:0.5em;
        }
    </style>


.. raw:: html

   <div style="float:right; margin:2em;">

.. image:: images/high-level-flocker-architecture.png
   :width: 150px

.. raw:: html

   </div>


.. what follows is a terrible hack to force sphinx to drag images into the build

.. raw:: html

   <div style="display:none;">

.. image:: _images/docker.png
.. image:: _images/kubernetes.png
.. image:: _images/mesos.png
   
.. raw:: html

   </div>

==============================================
How to include Flocker in your Container Stack
==============================================

**Flocker integrates container orchestration frameworks with storage systems.**

This means you can run *stateful containers* like *databases* in production and have the volumes follow the containers around as they get moved or rescheduled.

Flocker is filesystem-based, so it works with any container image that stores its data in a volume.

.. raw:: html

   <div style="clear:both;"></div>

.. _supported-orchestration-frameworks:

Supported Orchestration Frameworks
==================================

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="big-box">
	    Docker Engine, Swarm and/or Compose
		<img src="_images/docker.png" style="width:150px;"/>
		<br />
	<a href="docker-integration/" class="button" style="position:relative; top: 2em">Deploy</a>
    </div>
    <div class="big-box">
		<img src="_images/kubernetes.png" style="width:150px;"/>
        <br />
	<a href="kubernetes-integration/" class="button" style="position:relative; top: 2em">Deploy</a>
    </div>
    <div class="big-box">
		<img src="_images/mesos.png" style="width:150px;"/>
        <br />
	<a href="mesos-integration/" class="button" style="position:relative; top: 2em">Deploy</a>
    </div>
    <div class="big-box">
		Stand-alone Flocker
        <br />
	<a href="flocker-standalone/" class="button" style="position:relative; top: 2em">Deploy</a>
    </div>
    <div style="clear:both;"></div>

.. _storage-backends:

Supported Storage
=================

**IaaS block storage**

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="big-box">
        AWS - EBS
    </div>
    <div class="big-box">
        GCE - PD
    </div>
    <div class="big-box">
        OpenStack - Cinder
    </div>
    <div class="big-box">
        VMware vSphere (3rd party)
    </div>
    <div style="clear:both;"></div>

**Software defined storage**

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="small-box">
        Ceph (coming soon; experimental)
    </div>
    <div class="small-box">
        EMC ScaleIO (3rd party)
    </div>
    <div class="small-box">
        Hedvig (3rd party)
    </div>
    <div class="small-box">
        NexentaEdge (3rd party)
    </div>
    <div class="small-box">
        ConvergeIO (3rd party)
    </div>
    <div style="clear:both;"></div>
	
**Hardware devices**

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="small-box">
        Dell SC Series (3rd party)
    </div>
    <div class="small-box">
        EMC XtremIO (3rd party)
    </div>
    <div class="small-box">
        NetApp OnTap (3rd party)
    </div>
    <div class="small-box">
        Saratoga Speed (3rd party)
    </div>
    <div style="clear:both;"></div>
	
.. XXX This link probably needs to go somewhere, but not here: Configuration details for each of the backends can be found in the :ref:`Configuring the Nodes and Storage Backends<agent-yml>` topic.

.. note:: If you wish to use a storage device that is not supported by Flocker or an existing plugin, you can implement this support yourself.
          For more information, see :ref:`contribute-flocker-driver`.

.. _supported-operating-systems:

Supported Operating Systems
===========================

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="small-box">
        Ubuntu LTS
    </div>
    <div class="small-box">
        CentOS 7
    </div>
    <div class="small-box">
        RHEL 7 (coming soon)
    </div>
    <div class="small-box">
        CoreOS (beta)
    </div>
    <div style="clear:both;"></div>

.. toctree::
   :maxdepth: 2

   index
   docker-integration/index
   kubernetes-integration/index
   mesos-integration/index
   flocker-standalone/index
   labs/index
   releasenotes/index
   faq/index
   gettinginvolved/index

.. The version page is used only for a version of the documentation to know what the latest version is.

.. toctree::
   :hidden:

   version
