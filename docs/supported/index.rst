========================
Supported Configurations
========================

Supported Cluster Managers
==========================

.. raw:: html

	<div class="pods-eq">
	    <div class="pod-boxout pod-boxout--orchestration pod-boxout--recommended">
			<img src="/_images/docker2x.png" alt="Docker logo"/>
			<span>Docker, Swarm, Compose <em>Fastest</em></span>
	        <a href="docker-integration/" class="button button--fast">Learn more</a>
	    </div>
	    
	    <div class="pod-boxout pod-boxout--orchestration">
			<img src="/_images/kubernetes2x.png" alt="Kubernetes logo"/>
			<span>Kubernetes</span>
	        <a href="kubernetes-integration/" class="button">Learn more</a>
	    </div>
	    
	    <div class="pod-boxout pod-boxout--orchestration">
			<img src="/_images/mesos2x.png" alt="mesos logo"/>
			<span>Mesos</span>
	        <a href="mesos-integration/" class="button">Learn more</a>
	    </div>
	</div>
	
	 <div class="pod-boxout pod-boxout--minor pod-boxout--orchestration">
		<span><img src="/_images/icon-question2x.png" aria-hidden="true" alt=""/>&nbsp; You can install Flocker without a specific Cluster Manager</span>
        <a href="/flocker-standalone/" class="button">Learn more</a>
    </div>

.. _storage-backends:

Supported Infrastructure & Storage
==================================

The sections below list the supported infrastructure and storage options.

**Community Supported** are provided and supported by our community partners.
Other options that are still be worked on by ClusterHQ are tagged with **Experimental** or **Coming Soon**:

.. raw:: html
	
	<ul class="icon-key">
    	<li><img class="icon-key__ico" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>Community Supported</li>
		<li><img class="icon-key__ico" src="../_static/images/icon-labs2x.png" aria-hidden="true" alt=""/>Experimental</li>
		<li><img class="icon-key__ico" src="../_static/images/icon-soon2x.png" aria-hidden="true" alt=""/>Coming Soon</li>
	</ul>

IaaS Block Storage
==================

These are the best options for running Flocker on a supported public or private cloud.

.. raw:: html
	
	<div class="pods-eq">
		 <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="/_images/AWS.png" alt="Amazon AWS Logo"/>
			<span>Works with everything</span>
	        <a href="index.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/openstack2x.png" alt="Openstack logo"/>
			<span>Works with manual installation</span>
	        <a href="index.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/vmware2x.png" alt="VMWare logo"/>
			<span>VMware vSphere</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/vmware-configuration.html" class="button">Learn more</a>
	    </div>
	     <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/gce2x.png" alt="GCE logo"/>
			<span>GCE PD</span>
			<img class="icon-key-assign" src="../_static/images/icon-soon2x.png" aria-hidden="true" alt=""/>
	        <div class="button button--disabled">Coming soon</div>
	    </div>
	</div>
	
	
	<!--
    <div class="big-box storage">
        AWS EBS
		<img src="/_images/AWS.png" style="width:120px;"/>
        <p style="margin-top:10px"><a href="index.html">Works with everything</a></p>
    </div>
    
    <div class="big-box storage">
        OpenStack Cinder
		<img src="/_images/openstack.png" style="width:60px;"/>
        <p style="margin-top:10px"><a href="index.html">Works with manual installation</a></p>
    </div>
    <div class="big-box storage">
        VMware vSphere
		<img src="/_images/vmware.png" style="width:100px;"/>
		<br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/vmware-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        GCE PD
        <br />
		<img src="/_images/GCE.png" style="width:80px;"/>
        <img src="/_images/coming-soon.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Coming soon">
        <p style="margin-top:10px">Coming soon</p>
    </div>
    <div style="clear:both;"></div>
    
    -->

Software Defined Storage
========================

These software defined storage options can be run on any infrastructure, including bare metal.

.. raw:: html

	<div class="pods-eq">
		 <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="/_images/AWS.png" alt="Amazon AWS Logo"/>
			<span>Ceph</span>
			<img class="icon-key-assign" src="../_static/images/icon-labs2x.png" aria-hidden="true" alt=""/>
	        <a href="https://github.com/ClusterHQ/ceph-/flocker-driver" class="button">GitHub Repo</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/openstack2x.png" alt="OpenStack Logo"/>
			<span>ScaleIO</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/emc-configuration.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/vmware2x.png" alt="VMWare Logo"/>
			<span>Hedvig</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/hedvig-configuration.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/gce2x.png" alt="GCE logo"/>
			<span>NexentaEdge</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/nexenta-configuration.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/gce2x.png" alt="GCE logo"/>
			<span>ConvergeIO</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/convergeio-configuration.html" class="button">Learn more</a>
	    </div>
	</div>
	
	<!--
    <div class="big-box storage">
        Ceph
        <br />
		<img src="/_images/ceph.png" style="width:30px; "/>
        <br />
        <img src="/_images/experimental.png" style="height:25px; padding:2px 4px; border:1px solid #ddd;" title="Experimental (labs project)">
        <p style="margin-top:10px"><a href="https://github.com/ClusterHQ/ceph-/flocker-driver" target="/_blank">GitHub Repo</a></p>
    </div>
    <div class="big-box storage">
        ScaleIO
        <br />
		<img src="/_images/emc.png" style="width:50px;" title="EMC" />
        <br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/emc-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        Hedvig
        <br />
		<img src="/_images/hedvig.png" style="width:80px;" title="Hedvig" />
        <br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/hedvig-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        NexentaEdge
        <br />
		<img src="/_images/nexenta.png" style="width:60px;" title="Nexenta" />
        <br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/nexenta-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        ConvergeIO
        <br />
		<img src="/_images/convergeio.png" style="width:60px;" title="ConvergeIO" />
        <br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/convergeio-configuration.html">Learn more</a></p>
    </div>
    <div style="clear:both;"></div>
    -->

Hardware Storage Devices
========================

These hardware storage options require specific physical hardware in your data center.

.. raw:: html

	<div class="pods-eq">
		 <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="/_images/AWS.png" alt="Amazon AWS Logo"/>
			<span>Dell SC Series</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/dell-configuration.html" class="button">GitHub Repo</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/openstack2x.png" alt="OpenStack Logo"/>
			<span>EMC XtremIO, VMAX</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/emc-configuration.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/gce2x.png" alt="GCE logo"/>
			<span>NetApp OnTap</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/netapp-configuration.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/gce2x.png" alt="GCE logo"/>
			<span>Saratoga Speed</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/saratogaspeed-configuration.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/gce2x.png" alt="GCE logo"/>
			<span>Huawei</span>
			<img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
	        <a href="/flocker-features/huawei.html" class="button">Learn more</a>
	    </div>
	</div>

	<!--
    <div class="big-box storage">
        Dell SC Series
        <br />
		<img src="/_images/dell.png" style="height:35px;"/>
        <br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/dell-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        EMC XtremIO, VMAX
        <br />
		<img src="/_images/emc.png" style="width:50px;"/>
        <br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/emc-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        NetApp OnTap
        <br />
		<img src="/_images/netapp.png" style="width:20px;"/>
        <br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/netapp-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        Saratoga Speed
        <br />
		<img src="/_images/saratoga.png" style="width:50px;"/>
        <br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/saratogaspeed-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        Huawei
        <br />
		<img src="/_images/huawei.png" style="width:50px;"/>
        <br />
        <img src="/_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="/flocker-features/huawei.html">Learn more</a></p>
    </div>
    <div style="clear:both;"></div>
    <div style="clear:both; margin-top:20px;"></div>
   
   -->

.. note:: If you wish to use a storage device that is not supported by Flocker or an existing plugin, you can implement this support yourself.
          For more information, see :ref:`contribute-flocker-driver`.

.. _supported-operating-systems:

Supported Operating Systems
===========================

.. raw:: html

	<div class="pods-eq">
		 <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="/_images/AWS.png" alt="Amazon AWS Logo"/>
			<span>Works with everything</span>
	        <a href="index.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/openstack2x.png" alt="OpenStack Logo"/>
			<span>Works with manual installation</span>
	        <a href="index.html" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/vmware2x.png" alt="VMWare Logo"/>
			<span>Works with Labs Installer</span>
			<img class="icon-key-assign" src="../_static/images/icon-labs2x.png" aria-hidden="true" alt=""/>
	        <a href="flocker-standalone/installer.html#experimental-configurations" class="button">Learn more</a>
	    </div>
	    <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
			<img src="../_static/images/gce2x.png" alt="GCE logo"/>
			<span>RHEL 7</span>
			<img class="icon-key-assign" src="../_static/images/icon-soon2x.png" aria-hidden="true" alt=""/>
	        <div class="button button--disabled">Coming soon</div>
	    </div>
	</div>
	
	<!--
    <div class="big-box">
        Ubuntu 14.04
        <br />
		<img src="/_images/ubuntu.png" style="width:50px;"/>
        <p style="margin-top:10px"><a href="index.html">Works with everything</a></p>
    </div>
    <div class="big-box">
        CentOS 7
        <br />
		<img src="/_images/centos.png" style="width:60px;"/>
        <p style="margin-top:10px"><a href="index.html">Works with manual installation</a></p>
    </div>
    <div class="big-box">
        CoreOS
        <br />
		<img src="/_images/coreos.png" style="width:40px;"/>
        <br />
        <img src="/_images/experimental.png" style="height:25px; padding:2px 4px; border:1px solid #ddd;" title="Experimental (labs project)">
        <p style="margin-top:10px"><a href="/flocker-standalone/installer.html#experimental-configurations">Works with Labs Installer</a></p>
    </div>
    <div class="big-box">
        RHEL 7
        <br />
		<img src="/_images/rhel.png" style="width:40px;"/>
        <br />
        <img src="/_images/coming-soon.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Coming soon">
        <p style="margin-top:10px">Coming soon</p>
    </div>
    <div style="clear:both;"></div>
    -->

Running Flocker in Containers
=============================

It is possible to run Flocker in a container as an experimental configuration, click :ref:`here <flocker-containers>` to learn more.

.. toctree::
   :hidden:

   flockercontainers

.. What follows is a hack to force sphinx to drag images into the build

.. raw:: html

   <div style="display:none;">

.. image:: /images/docker.png
.. image:: /images/kubernetes.png
.. image:: /images/mesos.png
.. image:: /images/questionmark.png
.. image:: /images/AWS.png
.. image:: /images/GCE.png
.. image:: /images/vmware.png
.. image:: /images/openstack.png
.. image:: /images/3rd-party.png
.. image:: /images/coming-soon.png
.. image:: /images/experimental.png
.. image:: /images/ceph.png
.. image:: /images/emc.png
.. image:: /images/hedvig.png
.. image:: /images/nexenta.png
.. image:: /images/convergeio.png
.. image:: /images/dell.png
.. image:: /images/netapp.png
.. image:: /images/saratoga.png
.. image:: /images/huawei.png
.. image:: /images/ubuntu.png
.. image:: /images/centos.png
.. image:: /images/rhel.png
.. image:: /images/coreos.png

.. raw:: html

   </div>
