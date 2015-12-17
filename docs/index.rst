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

   <div style="float:right">

.. image:: images/puzzle_pieces.png
   :width: 150px

.. raw:: html

   </div>

How to include Flocker in your Container Stack
==============================================

**Flocker integrates container orchestration frameworks with storage systems.**

This means you can run *stateful containers* like *databases* in production and have the volumes follow the containers around as they get moved or rescheduled.

Flocker is filesystem-based, so it works with any container image that stores its data in a volume.

.. raw:: html

   <div style="clear:both;"></div>

==================================
Supported Orchestration Frameworks
==================================

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="big-box">
        Docker Engine, Swarm and/or Compose
    </div>
    <div class="big-box">
        Kubernetes
    </div>
    <div class="big-box">
        Mesos
    </div>
    <div class="big-box">
        Flocker Standalone
    </div>
    <div style="clear:both;"></div>

=================
Supported Storage
=================

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="small-box">
        AWS - EBS
    </div>
    <div class="small-box">
        GCE - PD
    </div>
    <div class="small-box">
        OpenStack - Cinder
    </div>
    <div class="small-box">
        vSphere - vSphere
    </div>
    <div class="small-box">
        Storage hardware e.g. Dell, EMC, NetApp (SAN) <link>
    </div>
    <div class="small-box">
        Storage software e.g. Ceph, ScaleIO (SDS) <link>
    </div>
    <div style="clear:both;"></div>

===========================
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

   introduction/index
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
