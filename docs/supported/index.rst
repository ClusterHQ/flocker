========================
Supported Configurations
========================

Supported Cluster Managers
==========================

.. raw:: html

        <div class="pods-eq">
            <div class="pod-boxout pod-boxout--orchestration pod-boxout--recommended">
                        <img src="../_static/images/docker2x.png" alt="Docker logo"/>
                        <span>Docker Swarm, with Docker Compose</span>
                <a href="../docker-integration/" class="button button--fast">Learn more</a>
            </div>

            <div class="pod-boxout pod-boxout--orchestration">
                        <img src="../_static/images/kubernetes2x.png" alt="Kubernetes logo"/>
                        <span>Kubernetes</span>
                <a href="../kubernetes-integration/" class="button">Learn more</a>
            </div>

            <div class="pod-boxout pod-boxout--orchestration">
                        <img src="../_static/images/mesos2x.png" alt="mesos logo"/>
                        <span>Mesos</span>
                <a href="../mesos-integration/" class="button">Learn more</a>
            </div>
        </div>

         <div class="pod-boxout pod-boxout--minor pod-boxout--orchestration">
                <span><img src="../_static/images/icon-question2x.png" aria-hidden="true" alt=""/>&nbsp; You can install Flocker without a specific Cluster Manager</span>
        <a href="../flocker-standalone/" class="button">Learn more</a>
    </div>

.. _storage-backends:

Supported Infrastructure & Storage
==================================

The sections below list the supported infrastructure and storage options.

.. raw:: html

        <ul class="icon-key">
        <li><img class="icon-key__ico" src="../_static/images/icon-community2x.png" aria-hidden="true" alt="Community supported"/><strong>Community Supported</strong>: provided by and supported by our community partners.</li>
                <li><img class="icon-key__ico" src="../_static/images/icon-labs2x.png" aria-hidden="true" alt="Experimental"/><strong>Experimental</strong>: developed to less rigorous quality and testing standards.</li>
                <li><img class="icon-key__ico" src="../_static/images/icon-soon2x.png" aria-hidden="true" alt="Coming soon"/><strong>Coming Soon</strong>: we're working on it!</li>
        </ul>

IaaS Block Storage
==================

These are the best options for running Flocker on a supported public or private cloud.

.. raw:: html

        <div class="pods-eq">
                 <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/AWS.png" alt="Amazon AWS Logo"/>
                        <span>AWS EBS</span>
                <a href="../flocker-features/aws-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/openstack2x.png" alt="Openstack logo"/>
                        <span>OpenStack Cinder</span>
                <a href="../flocker-features/openstack-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/gce2x.png" alt="GCE logo"/>
                        <span>GCE PD</span>
                <a href="../flocker-features/gce-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/vmware2x.png" alt="VMWare logo"/>
                        <span>VMware vSphere</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/vmware-configuration.html" class="button">Learn more</a>
            </div>
        </div>


Software Defined Storage
========================

These software defined storage options can be run on any infrastructure, including bare metal.

.. raw:: html

        <div class="pods-eq">
                 <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/ceph2x.png" alt="Ceph Logo"/>
                        <span>Ceph</span>
                        <img class="icon-key-assign" src="../_static/images/icon-labs2x.png" aria-hidden="true" alt=""/>
                <a href="https://github.com/ClusterHQ/ceph-flocker-driver" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/emc2x.png" alt="EMC Logo"/>
                        <span>ScaleIO</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/emc-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/hedvig2x.png" alt="Hedvig Logo"/>
                        <span>Hedvig</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/hedvig-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/nexenta2x.png" alt="NexentaEdge logo"/>
                        <span>NexentaEdge</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/nexenta-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/convergeio2x.png" alt="convergeio logo"/>
                        <span>ConvergeIO</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/convergeio-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/open-vstorage.png" alt="open-vstorage logo"/>
                        <span>Open vStorage</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/open-vstorage-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/coprhd.png" alt="CoprHD logo"/>
                        <span>CoprHD</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/coprhd-configuration.html" class="button">Learn more</a>
            </div>
        </div>


Hardware Storage Devices
========================

These hardware storage options require specific physical hardware in your data center.

.. raw:: html

        <div class="pods-eq">
                 <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/dell2x.png" alt="Dell Logo"/>
                        <span>Dell SC Series</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/dell-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/emc2x.png" alt="EMC Logo"/>
                        <span>EMC XtremIO, VMAX</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/emc-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/netapp2x.png" alt="Netapp logo"/>
                        <span>NetApp OnTap</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/netapp-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/saratoga2x.png" alt="Saratoga logo"/>
                        <span>Saratoga Speed</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/saratogaspeed-configuration.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/huawei2x.png" alt="Huawei logo"/>
                        <span>Huawei</span>
                        <img class="icon-key-assign" src="../_static/images/icon-community2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-features/huawei-configuration.html" class="button">Learn more</a>
            </div>
        </div>

.. note:: If you wish to use a storage device that is not supported by Flocker or an existing plugin, you can implement this support yourself.
          For more information, see :ref:`contribute-flocker-driver`.

.. _supported-operating-systems:

Supported Operating Systems
===========================

.. raw:: html

        <div class="pods-eq">
                 <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/ubuntu2x.png" alt="Ubuntu Logo"/>
                        <span>Ubuntu 14.04</span>
                <a href="../index.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/centos2x.png" alt="CentOS Logo"/>
                        <span>CentOS 7</span>
                <a href="../index.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/rhel72x.png" alt="RHEL 7 logo"/>
                        <span>RHEL 7</span>
                <a href="../index.html" class="button">Learn more</a>
            </div>
            <div class="pod-boxout pod-boxout--4up pod-boxout--orchestration">
                        <img src="../_static/images/coreos2x.png" alt="CoreOS Logo"/>
                        <span>CoreOS</span>
                        <img class="icon-key-assign" src="../_static/images/icon-labs2x.png" aria-hidden="true" alt=""/>
                <a href="../flocker-standalone/installer.html#experimental-configurations" class="button">Learn more</a>
            </div>
        </div>

Running Flocker in Containers
=============================

It is possible to run Flocker in a container as an experimental configuration, click :ref:`here <flocker-containers>` to learn more.

.. toctree::
   :hidden:

   flockercontainers
