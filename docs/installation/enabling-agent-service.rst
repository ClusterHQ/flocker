.. Single Source Instructions

==================================
Enabling the Flocker Agent Service
==================================

.. begin-body-enable-agent-intro

The ``flocker-dataset-agent`` is the workhorse of Flocker; you should enable and run it on each node in your cluster.

.. end-body-enable-agent-intro

.. begin-body-enable-agent-main

CentOS 7, RHEL 7.2
==================

#. Run the following commands to enable the agent service:

   .. task:: enable_flocker_agent centos-7
      :prompt: [root@agent-node]#

#. Run the following commands to enable the Flocker plugin for Docker:

   .. prompt:: bash [root@agent-node]#

      systemctl enable flocker-docker-plugin
      systemctl restart flocker-docker-plugin

Ubuntu 16.04
============

#. Run the following commands to enable the agent service:

   .. task:: enable_flocker_agent ubuntu-16.04
      :prompt: [root@agent-node]#

#. Run the following command to enable the Flocker plugin for Docker:

   .. prompt:: bash [root@agent-node]#

      systemctl enable flocker-docker-plugin
      systemctl restart flocker-docker-plugin

Ubuntu 14.04
============

#. Run the following commands to enable the agent service:

   .. task:: enable_flocker_agent ubuntu-14.04
      :prompt: [root@agent-node]#

#. Run the following command to enable the Flocker plugin for Docker:

   .. prompt:: bash [root@agent-node]#

      service flocker-docker-plugin restart

.. end-body-enable-agent-main

.. begin-body-enable-agent-other

CentOS 7, RHEL 7.2
==================

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent centos-7
      :prompt: [root@agent-node]#

Ubuntu 16.04
============

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent ubuntu-16.04
      :prompt: [root@agent-node]#

Ubuntu 14.04
============

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent ubuntu-14.04
      :prompt: [root@agent-node]#

.. end-body-enable-agent-other
