===================================
Flocker with Docker, Swarm, Compose
===================================

Deployment options
==================

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
        <a href="cloudformation.html" class="button">Install</a>
    </div>
    <div class="wide-box">
        &lt;other installation options go here...&gt;
    </div>


About the integration
=====================

Flocker integrates with the Docker Engine, Docker Swarm and/or Docker Compose via the Flocker Plugin for Docker.

The Flocker Plugin for Docker is a Docker volumes plugin.

It allows you to control Flocker directly from the Docker CLI or a Docker Compose file.

It also works in multi-host environments where you're using Docker Swarm.

Tutorials
=========

* Using the Flocker plugin for Docker directly
* Flocker with Docker Swarm and Compose

.. toctree::
   :maxdepth: 2

   cloudformation
