.. begin-body

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

.. _storage-backends:

Supported Storage
=================

Flocker allows you to use either shared storage, like Amazon EBS or EMC ScaleIO, or local storage for your application’s storage layer.
The best option for you depends on a combination of factors including where you run your application and the capabilities you are trying to achieve.

For help determining which storage option is right for you, you will find a useful table in the `storage section of our About Flocker`_ page. 

ClusterHQ supported drivers:

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
    <div style="clear:both;"></div>

Community supported drivers:

.. raw:: html

    <!-- This too needs to become Sphinx directives, rather than raw HTML. -->
    <div class="small-box">
        ConvergeIO
    </div>
    <div class="small-box">
        Dell SC Series
    </div>
    <div class="small-box">
        EMC ScaleIO
    </div>
    <div class="small-box">
        EMC XtremIO
    </div>
    <div class="small-box">
        Hedvig
    </div>
    <div class="small-box">
        NetApp OnTap
    </div>
    <div class="small-box">
        NexentaEdge
    </div>
    <div class="small-box">
        Saratoga Speed
    </div>
    <div class="small-box">
        VMware
    </div>
    <div style="clear:both;"></div>

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

Configuration details for each of the backends can be found in the :ref:`Configuring the Nodes and Storage Backends<agent-yml>` topic.

.. note:: If you wish to use a storage device that is not supported by Flocker or an existing plugin, you can implement this support yourself.
          For more information, see :ref:`contribute-flocker-driver`.

.. _storage section of our About Flocker: https://clusterhq.com/flocker/introduction/#storage-options

.. end-body

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
