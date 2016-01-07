.. raw:: html

    <style>
        .toctree-wrapper { display:none; }
        h1 { display:none; }
    </style>

.. _storage-backends:

========================
Supported Configurations
========================

Supported Orchestration Frameworks
==================================

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="big-box orchestration">
	    Docker, Swarm, Compose
		<img src="_images/docker.png" style="width:50px;"/>
		<br />
    </div>
    <div class="big-box orchestration">
		Kubernetes
		<img src="_images/kubernetes.png" style="width:50px;"/>
        <br />
    </div>
    <div class="big-box orchestration">
		Mesos
		<img src="_images/mesos.png" style="width:50px;"/>
        <br />
    </div>
    <div class="big-box orchestration">
		Other
	 	<img src="_images/questionmark.png" style="width:50px;"/>
        <br />
    </div>
    <div style="clear:both;"></div>


Supported Infrastructure & Storage
==================================

**IaaS block storage**

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="big-box storage">
        AWS EBS
		<img src="_images/AWS.png" style="width:120px;"/>
    </div>
    <div class="big-box storage">
        GCE PD
        <br />
		<img src="_images/GCE.png" style="width:80px;"/>
        <img src="_images/coming-soon.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Coming soon">
    </div>
    <div class="big-box storage">
        OpenStack Cinder
		<img src="_images/openstack.png" style="width:100px;"/>
    </div>
    <div class="big-box storage">
        VMware vSphere
		<img src="_images/vmware.png" style="width:100px;"/>
		<br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div style="clear:both;"></div>

**Software defined storage**

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="small-box storage">
		<img src="_images/ceph.png" style="width:30px; "/>
        Ceph
        <br />
        <img src="_images/coming-soon.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Coming soon">
        <img src="_images/experimental.png" style="height:25px; padding:2px 4px; border:1px solid #ddd;" title="Experimental (labs project)">
    </div>
    <div class="small-box storage">
		<img src="_images/emc.png" style="width:50px;" title="EMC" />
        ScaleIO
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div class="small-box storage">
		<img src="_images/hedvig.png" style="width:80px;" title="Hedvig" />
        Hedvig
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div class="small-box storage">
		<img src="_images/nexenta.png" style="width:60px;" title="Nexenta" />
        NexentaEdge
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div class="small-box storage">
		<img src="_images/convergeio.png" style="width:60px;" title="ConvergeIO" />
        ConvergeIO
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div style="clear:both;"></div>

**Hardware devices**

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="small-box storage">
		<img src="_images/dell.png" style="height:35px;"/><br />SC Series
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div class="small-box storage">
		<img src="_images/emc.png" style="width:50px;"/> XtremIO
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div class="small-box storage">
		<img src="_images/netapp.png" style="width:20px;"/> NetApp OnTap
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div class="small-box storage">
		<img src="_images/saratoga.png" style="width:50px;"/>
        Saratoga Speed
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div class="small-box storage">
		<img src="_images/huawei.png" style="width:50px;"/>
        Huawei
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
    </div>
    <div style="clear:both;"></div>
    <div style="clear:both; margin-top:20px;"></div>

    <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed"> = Community developed
    <img src="_images/experimental.png" style="height:25px; padding:2px 4px; margin-left:20px; border:1px solid #ddd;" title="Experimental (labs project)"> = Experimental
    <img src="_images/coming-soon.png" style="height:25px; margin:2px; margin-left:20px; border:1px solid #ddd;" title="Coming soon"> = Coming soon
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
		<img src="_images/centos.png" style="width:60px;"/>
    </div>
    <div class="small-box">
        RHEL 7
		<img src="_images/rhel.png" style="width:40px;"/>
        <br />
        <img src="_images/coming-soon.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Coming soon">
    </div>
    <div class="small-box">
        CoreOS
		<img src="_images/coreos.png" style="width:40px;"/>
        <br />
        <img src="_images/experimental.png" style="height:25px; padding:2px 4px; border:1px solid #ddd;" title="Experimental (labs project)">
    </div>
    <div style="clear:both;"></div>


.. What follows is a terrible hack to force sphinx to drag images into the build

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
