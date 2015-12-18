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
            padding:0.5em;
        }
        .small-box {
            border:1px solid black;
            width:7em;
            height:7em;
            float:left;
            margin:0.5em;
            padding:0.5em;
        }
        .orchestration {
            border-color: #80B164;
        }
        .storage {
            border-color: #D69A00;
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

.. image:: images/docker.png
.. image:: images/kubernetes.png
.. image:: images/mesos.png
.. image:: images/questionmark.png
.. image:: images/AWS.png
.. image:: images/GCE.png
.. image:: images/vmware.png
.. image:: images/openstack.png
.. image:: images/3rd-party.png
.. image:: images/coming-soon.png
.. image:: images/experimental.png
.. image:: images/ceph.png
.. image:: images/emc.png
.. image:: images/hedvig.png
.. image:: images/nexenta.png
.. image:: images/convergeio.png
.. image:: images/dell.png
.. image:: images/netapp.png
.. image:: images/saratoga.png
.. image:: images/huawei.png
.. image:: images/ubuntu.png
.. image:: images/centos.png
.. image:: images/rhel.png
.. image:: images/coreos.png

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
    <div class="big-box orchestration">
	    Docker, Swarm, Compose
		<img src="_images/docker.png" style="width:50px;"/>
		<br />
	<a href="docker-integration/" class="button" style="position:relative; top: 2em">Deploy</a>
    </div>
    <div class="big-box orchestration">
		Kubernetes
		<img src="_images/kubernetes.png" style="width:50px;"/>
        <br />
	<a href="kubernetes-integration/" class="button" style="position:relative; top: 2em">Deploy</a>
    </div>
    <div class="big-box orchestration">
		Mesos
		<img src="_images/mesos.png" style="width:50px;"/>
        <br />
	<a href="mesos-integration/" class="button" style="position:relative; top: 2em">Deploy</a>
    </div>
    <div class="big-box orchestration">
		Other
	 	<img src="_images/questionmark.png" style="width:50px;"/>
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
    <div class="big-box storage">
        AWS - EBS
		<img src="_images/AWS.png" style="width:50px;"/>
    </div>
    <div class="big-box storage">
        GCE - PD
		<img src="_images/GCE.png" style="width:50px;"/>
		(coming soon)
    </div>
    <div class="big-box storage">
        OpenStack - Cinder
		<img src="_images/openstack.png" style="width:50px;"/>
    </div>
    <div class="big-box storage">
        VMware vSphere
		<img src="_images/vmware.png" style="width:50px;"/>
		<br />
    </div>
    <div style="clear:both;"></div>

**Software defined storage**

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="small-box storage">
        Ceph 
		<img src="_images/ceph.png" style="width:50px;"/>
		(coming soon)
		(experimental)
    </div>
    <div class="small-box storage">
        EMC ScaleIO
		<img src="_images/emc.png" style="width:50px;"/>
		(3rd party)
    </div>
    <div class="small-box storage">
        Hedvig
		<img src="_images/hedvig.png" style="width:50px;"/>
		(3rd party)
    </div>
    <div class="small-box storage">
        NexentaEdge
		<img src="_images/nexenta.png" style="width:50px;"/>
		(3rd party)
    </div>
    <div class="small-box storage">
        ConvergeIO
		<img src="_images/convergeio.png" style="width:50px;"/>
		(3rd party)
    </div>
    <div style="clear:both;"></div>

**Hardware devices**

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="small-box storage">
        Dell SC Series
		<img src="_images/dell.png" style="width:50px;"/>
		(3rd party)
    </div>
    <div class="small-box storage">
        EMC XtremIO
		<img src="_images/emc.png" style="width:50px;"/>
		(3rd party)
    </div>
    <div class="small-box storage">
        NetApp OnTap
		<img src="_images/netapp.png" style="width:50px;"/>
		(3rd party)
    </div>
    <div class="small-box storage">
        Saratoga Speed
		<img src="_images/saratoga.png" style="width:50px;"/>
		(3rd party)
    </div>
    <div class="small-box storage">
        Huawei
		<img src="_images/huawei.png" style="width:50px;"/>
		(3rd party)
    </div>
    <div style="clear:both;"></div>
    <div style="clear:both; margin-top:20px;"></div>

    <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed (3rd party)"> = Community developed (3rd party)
    <img src="_images/experimental.png" style="height:25px; padding:2px 4px; border:1px solid #ddd;" title="Experimental (labs project)"> = Experimental
    <img src="_images/coming-soon.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Coming soon"> = Coming soon
    <div style="clear:both; margin-top:20px;"></div>

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
		<img src="_images/ubuntu.png" style="width:50px;"/>
    </div>
    <div class="small-box">
        CentOS 7
		<img src="_images/centos.png" style="width:50px;"/>
    </div>
    <div class="small-box">
        RHEL 7
		<img src="_images/rhel.png" style="width:50px;"/>
		(coming soon)
    </div>
    <div class="small-box">
        CoreOS
		<img src="_images/coreos.png" style="width:50px;"/>
		(beta)
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
