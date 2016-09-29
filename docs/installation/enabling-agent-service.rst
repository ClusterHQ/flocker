.. Single Source Instructions

==================================
Enabling the Flocker Agent Service
==================================

.. begin-body-enable-agent-intro

The ``flocker-dataset-agent`` is the workhorse of Flocker; you install an agent on each node in your cluster, and enabling them is an essential step in setting up your cluster.

.. note:: The ``flocker-container-agent`` is now deprecated, but it can still be enabled.
   For more information, see :ref:`deprecated-endpoints`.

.. end-body-enable-agent-intro

.. begin-body-enable-agent-main

CentOS 7, RHEL 7.2
==================

#. Run the following commands to enable the agent service:

   .. prompt:: bash [root@agent-node]#
   
      systemctl enable flocker-dataset-agent
      systemctl start flocker-dataset-agent

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

   .. prompt:: bash [root@agent-node]#

      service flocker-dataset-agent start

#. Run the following command to enable the Flocker plugin for Docker:

   .. prompt:: bash [root@agent-node]#

      service flocker-docker-plugin restart

.. end-body-enable-agent-main

.. begin-body-enable-agent-other

CentOS 7, RHEL 7.2
==================

Run the following commands to enable the agent service:

.. prompt:: bash [root@agent-node]#
   
   systemctl enable flocker-dataset-agent
   systemctl start flocker-dataset-agent

Ubuntu 16.04
============

Run the following commands to enable the agent service:

.. task:: enable_flocker_agent ubuntu-16.04
      :prompt: [root@agent-node]#

Ubuntu 14.04
============

Run the following command to enable the agent service:

.. prompt:: bash [root@agent-node]#

   service flocker-dataset-agent start

.. end-body-enable-agent-other
