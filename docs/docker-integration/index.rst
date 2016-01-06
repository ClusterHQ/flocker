=====================================
> Flocker with Docker, Swarm, Compose
=====================================

Install Flocker
===============

.. raw:: html

    <!-- This toctree-wrapper and next button override is obviously a horrible
         hack, and we need a better way of disabling the toctree on the front
         page. -->
    <style>
        .toctree-wrapper { display:none; }
        a.button.rel { display:none; }
        .wide-box {
            border:1px solid black;
            width:45%;
            height:10em;
            float:left;
            margin:0.5em;
            padding:0.5em;
        }
    </style>

    <div class="wide-box" style="background-color:yellow;">
        CloudFormation is the easiest way to get started with Flocker and Swarm on AWS.
        <br />
        <br />
        <a href="cloudformation.html" class="button">CloudFormation Install</a>
    </div>
    <div class="wide-box">
        Install Flocker manually to deploy it on infrastructure other than AWS.
        <br />
        <br />
        <a href="manual-install.html" class="button">Manual Install</a>
    </div>
    <div style="clear:both;"></div>


Follow a tutorial
=================

.. raw:: html

    <div class="wide-box" style="background-color:yellow;">
        Tutorial: using Flocker with Docker Swarm and Compose
        <br />
        <br />
        <a href="tutorial-swarm-compose.html" class="button">Follow Tutorial</a>
    </div>
    <div style="clear:both;"></div>

Learn more about the integration
================================

To learn about the details of how this integration works, read :ref:`about`.

.. toctree::
   :maxdepth: 2

   cloudformation
   about
