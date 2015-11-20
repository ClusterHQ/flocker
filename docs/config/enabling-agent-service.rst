.. _enabling-agent-service:

==================================
Enabling the Flocker Agent Service
==================================

The Flocker agents, the ``flocker-dataset-agent`` and the ``flocker-container-agent``, are the workhorses of Flocker; you have them on each node in your cluster, and enabling them is an essential step in setting up your cluster.

:ref:`docker-plugin` (``flocker-docker-plugin``) is also installed on each node in the cluster.
The instructions below include enabling and testing the plugin, which allows Flocker to manage your data volumes while using other tools such as Docker, Docker Swarm, or Mesos to manage your containers.

.. note::
   Flocker's container management features depend on Docker.
   You will need to make sure `Docker (at least 1.8) is installed`_ and running before you enable ``flocker-container-agent``.

CentOS 7
========

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

Testing the Flocker Plugin for Docker
=====================================

Once installed, the example provided below runs two simple Docker tests to verify that the plugin is working correctly with the Flocker agents.

#. Run the following command, which uses the Flocker plugin for Docker as the volume driver to create a named volume called ``apples``:

   .. prompt:: bash $

      docker run -v apples:/data --volume-driver flocker busybox sh -c "echo hello > /data/file.txt"

#. Run the following command to reattach the same volume from the first container, and verify that the data (``hello``) has been preserved.

   .. prompt:: bash $

      docker run -v apples:/data --volume-driver flocker busybox sh -c "cat /data/file.txt"

More information about using the Flocker plugin for Docker can be found in :ref:`using-docker-plugin`.

Next Steps
==========

The configuration of your Flocker cluster is now complete.
To learn about controlling and administering Flocker, please move on to :ref:`controlling-flocker`.

.. _Docker (at least 1.8) is installed: https://docs.docker.com/installation/
