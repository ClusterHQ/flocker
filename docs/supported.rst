========================
Supported Configurations
========================

Supported Orchestration Frameworks
==================================

.. raw:: html

	<div class="pods-eq">
	    <div class="pod-boxout pod-boxout--orchestration pod-boxout--recommended">
			<img src="_images/docker2x.png" alt="Docker logo"/>
			<span>Docker, Swarm, Compose <em>Fastest</em></span>
	        <a href="docker-integration/" class="button button--fast">Learn more</a>
	    </div>
	    
	    <div class="pod-boxout pod-boxout--orchestration">
			<img src="_images/kubernetes2x.png" alt="Kubernetes logo"/>
			<span>Kubernetes</span>
	        <a href="kubernetes-integration/" class="button">Learn more</a>
	    </div>
	    
	    <div class="pod-boxout pod-boxout--orchestration">
			<img src="_images/mesos2x.png" alt="mesos logo"/>
			<span>Mesos</span>
	        <a href="mesos-integration/" class="button">Learn more</a>
	    </div>
	</div>
	
	 <div class="pod-boxout pod-boxout--minor pod-boxout--orchestration">
		<span><img src="_images/icon-question2x.png" aria-hidden="true" alt=""/>&nbsp;Install Flocker without an Orchestration Framework</span>
        <a href="flocker-standalone/" class="button">Learn more</a>
    </div>

.. _storage-backends:

Supported Infrastructure & Storage
==================================

IaaS block storage
------------------

These are the best options for running Flocker on a supported public or private cloud.

.. raw:: html

    <div class="big-box storage">
        AWS EBS
		<img src="_images/AWS.png" style="width:120px;"/>
        <p style="margin-top:10px"><a href="index.html">Works with everything</a></p>
    </div>
    <div class="big-box storage">
        OpenStack Cinder
		<img src="_images/openstack.png" style="width:60px;"/>
        <p style="margin-top:10px"><a href="index.html">Works with manual installation</a></p>
    </div>
    <div class="big-box storage">
        VMware vSphere
		<img src="_images/vmware.png" style="width:100px;"/>
		<br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/vmware-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        GCE PD
        <br />
		<img src="_images/GCE.png" style="width:80px;"/>
        <img src="_images/coming-soon.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Coming soon">
        <p style="margin-top:10px">Coming soon</p>
    </div>
    <div style="clear:both;"></div>

Software defined storage
------------------------

These software defined storage options can be run on any infrastructure, including bare metal.

.. raw:: html

    <div class="big-box storage">
        Ceph
        <br />
		<img src="_images/ceph.png" style="width:30px; "/>
        <br />
        <img src="_images/experimental.png" style="height:25px; padding:2px 4px; border:1px solid #ddd;" title="Experimental (labs project)">
        <p style="margin-top:10px"><a href="https://github.com/ClusterHQ/ceph-flocker-driver" target="_blank">GitHub Repo</a></p>
    </div>
    <div class="big-box storage">
        ScaleIO
        <br />
		<img src="_images/emc.png" style="width:50px;" title="EMC" />
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/emc-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        Hedvig
        <br />
		<img src="_images/hedvig.png" style="width:80px;" title="Hedvig" />
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/hedvig-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        NexentaEdge
        <br />
		<img src="_images/nexenta.png" style="width:60px;" title="Nexenta" />
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/nexenta-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        ConvergeIO
        <br />
		<img src="_images/convergeio.png" style="width:60px;" title="ConvergeIO" />
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/convergeio-configuration.html">Learn more</a></p>
    </div>
    <div style="clear:both;"></div>

Hardware storage devices
------------------------

These hardware storage options require specific physical hardware in your data center.

.. raw:: html

    <div class="big-box storage">
        Dell SC Series
        <br />
		<img src="_images/dell.png" style="height:35px;"/>
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/dell-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        EMC XtremIO, VMAX
        <br />
		<img src="_images/emc.png" style="width:50px;"/>
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/emc-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        NetApp OnTap
        <br />
		<img src="_images/netapp.png" style="width:20px;"/>
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/netapp-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        Saratoga Speed
        <br />
		<img src="_images/saratoga.png" style="width:50px;"/>
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/saratogaspeed-configuration.html">Learn more</a></p>
    </div>
    <div class="big-box storage">
        Huawei
        <br />
		<img src="_images/huawei.png" style="width:50px;"/>
        <br />
        <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed">
        <p style="margin-top:10px"><a href="flocker-standalone/huawei.html">Learn more</a></p>
    </div>
    <div style="clear:both;"></div>
    <div style="clear:both; margin-top:20px;"></div>

    <img src="_images/3rd-party.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Community developed"> = Community developed
    <img src="_images/experimental.png" style="height:25px; padding:2px 4px; margin-left:20px; border:1px solid #ddd;" title="Experimental (labs project)"> = Experimental
    <img src="_images/coming-soon.png" style="height:25px; margin:2px; margin-left:20px; border:1px solid #ddd;" title="Coming soon"> = Coming soon
    <div style="clear:both; margin-top:20px;"></div>

.. note:: If you wish to use a storage device that is not supported by Flocker or an existing plugin, you can implement this support yourself.
          For more information, see :ref:`contribute-flocker-driver`.

.. _supported-operating-systems:

Supported Operating Systems
===========================

.. raw:: html

    <div class="big-box">
        Ubuntu 14.04
        <br />
		<img src="_images/ubuntu.png" style="width:50px;"/>
        <p style="margin-top:10px"><a href="index.html">Works with everything</a></p>
    </div>
    <div class="big-box">
        CentOS 7
        <br />
		<img src="_images/centos.png" style="width:60px;"/>
        <p style="margin-top:10px"><a href="index.html">Works with manual installation</a></p>
    </div>
    <div class="big-box">
        CoreOS
        <br />
		<img src="_images/coreos.png" style="width:40px;"/>
        <br />
        <img src="_images/experimental.png" style="height:25px; padding:2px 4px; border:1px solid #ddd;" title="Experimental (labs project)">
        <p style="margin-top:10px"><a href="flocker-standalone/installer.html#experimental-configurations">Works with Labs Installer</a></p>
    </div>
    <div class="big-box">
        RHEL 7
        <br />
		<img src="_images/rhel.png" style="width:40px;"/>
        <br />
        <img src="_images/coming-soon.png" style="height:25px; margin:2px; border:1px solid #ddd;" title="Coming soon">
        <p style="margin-top:10px">Coming soon</p>
    </div>
    <div style="clear:both;"></div>


.. What follows is a hack to force sphinx to drag images into the build

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
