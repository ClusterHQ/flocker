.. Single Source Instructions

==================================
Enabling the Flocker Agent Service
==================================

.. begin-body-enable-agent-intro

The Flocker agents, the ``flocker-dataset-agent`` and the ``flocker-container-agent``, are the workhorses of Flocker; you have them on each node in your cluster, and enabling them is an essential step in setting up your cluster.

.. end-body-enable-agent-intro

.. begin-body-enable-agent-main

.. note::
   Flocker's container management features depend on Docker.
   You will need to make sure `Docker (at least 1.8) is installed`_ and running before you enable ``flocker-container-agent``.

.. _Docker (at least 1.8) is installed: https://docs.docker.com/installation/

CentOS 7, RHEL 7.2
==================

#. Run the following commands to enable the agent service:

   .. task:: enable_flocker_agent centos-7
      :prompt: [root@agent-node]#

#. Run the following commands to enable the Flocker plugin for Docker:

   .. prompt:: bash [root@agent-node]#
   
      systemctl enable flocker-docker-plugin
      systemctl restart flocker-docker-plugin

Ubuntu
======

#. Run the following commands to enable the agent service:

   .. task:: enable_flocker_agent ubuntu-14.04
      :prompt: [root@agent-node]#

#. Run the following command to enable the Flocker plugin for Docker:

   .. prompt:: bash [root@agent-node]#

      service flocker-docker-plugin restart

.. end-body-enable-agent-main

.. begin-body-enable-agent-other

.. note::
   Flocker's container management features depend on Docker.
   You will need to make sure `Docker (at least 1.8) is installed`_ and running before you enable ``flocker-container-agent``.

.. _Docker (at least 1.8) is installed: https://docs.docker.com/installation/

CentOS 7, RHEL 7.2
==================

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent centos-7
      :prompt: [root@agent-node]#

Ubuntu
======

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent ubuntu-14.04
      :prompt: [root@agent-node]#

.. end-body-enable-agent-other
