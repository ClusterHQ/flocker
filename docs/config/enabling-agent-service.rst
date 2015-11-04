==================================
Enabling the Flocker Agent Service
==================================

The Flocker agents, the ``flocker-dataset-agent`` and the ``flocker-container-agent``, are the workhorses of Flocker; you have them on each node in your cluster, and enabling them is an essential step in setting up your cluster:

CentOS 7
========

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent centos-7
   :prompt: [root@agent-node]#

Ubuntu
======

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent ubuntu-14.04
   :prompt: [root@agent-node]#
