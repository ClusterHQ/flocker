.. raw:: html

    <style>
        .toctree-wrapper { display:none; }
    </style>

====================
Flocker Integrations
====================

.. _supported-orchestration-frameworks:

Flocker allows you to launch and move stateful containers by integrating with a Cluster Manager of your choice.

Flocker integrates with a range of Cluster Managers.

Using Flocker with a Cluster Manager
====================================

For installation and configuration information for using Flocker with a cluster manager, first choose which integration you are using, or intend to use:

.. raw:: html

   <div class="pods-eq">
        <div class="pod-boxout pod-boxout--orchestration pod-boxout--recommended">
            <div class="heading-logo-lockup">    
            <p><strong>Docker Swarm, with Docker Compose</strong></p>
                <img src="_static/images/docker2x.png" alt="Docker logo"/>
        </div>
             <div class="bulleted-list">
        <p><em>Easiest way to install Flocker</em></p>
                <p>Plus:</p>
                <ul>
            <li>Tutorials</li>
                    <li>Blog Articles</li>
                    <li>Advanced Concepts</li>
           </ul>
            </div>
            <a href="docker-integration/" class="button button--fast">Use Flocker with Docker</a>
        </div>

        <div class="pod-boxout pod-boxout--orchestration">
        <div class="heading-logo-lockup">             
            <p><strong>Kubernetes</strong></p>
                <img src="_static/images/kubernetes2x.png" alt="Kubernetes logo"/>
        </div>
            <div class="bulleted-list">
        <p>How to install Flocker</p>
            <p>Plus:</p>
        <ul>
            <li>Tutorials</li>
            <li>Blog Articles</li>
        </ul>
            </div>
            <a href="kubernetes-integration/" class="button">Use Flocker with Kubernetes</a>
        </div>

        <div class="pod-boxout pod-boxout--orchestration">
        <div class="heading-logo-lockup">          
            <p><strong>Mesos</strong></p>
            <img src="_static/images/mesos2x.png" alt="mesos logo"/>
        </div>
             <div class="bulleted-list">
        <p>How to install Flocker</p>
            <p>Plus:</p>
        <ul>
            <li>Blog Articles</li>
        </ul>
            </div>
            <a href="mesos-integration/" class="button">Use Flocker with Mesos</a>
        </div>
   </div>


Using Flocker without a Cluster Manager
=======================================

Alternatively, if you want to install Flocker without a specific Cluster Manager in mind, that is also possible:

.. raw:: html

   <div class="pods-eq">
	    <div class="pod-boxout pod-boxout--2up pod-boxout--short">
		     <a href="flocker-standalone/" class="button">Use Flocker without a Cluster Manager</a>
	    </div>	
   </div>

Is your chosen Cluster Manager missing?
Please let us know with the form below!

.. toctree::
   :maxdepth: 2

   docker-integration/index
   kubernetes-integration/index
   mesos-integration/index
   flocker-standalone/index
   supported/index
   administering/index
   flocker-features/index
   reference/index
   releasenotes/index
   faq/index
   gettinginvolved/index

.. The version page is used only for a version of the documentation to know what the latest version is.

.. toctree::
   :hidden:

   version
   installation/index
