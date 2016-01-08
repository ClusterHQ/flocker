.. _enabling-agent-service-docker:

==================================
Enabling the Flocker Agent Service
==================================

.. include:: ../installation/enabling-agent-service.rst
   :start-after: .. begin-body-enable-agent-intro
   :end-before: .. end-body-enable-agent-intro

The :ref:`plugin` (``flocker-docker-plugin``) is also installed on each node in the cluster.
The instructions below include enabling and testing the plugin, which allows Flocker to manage your data volumes while using other tools such as Docker, Docker Swarm, or Mesos to manage your containers.

.. include:: ../installation/enabling-agent-service.rst
   :start-after: .. begin-body-enable-agent-main
   :end-before: .. end-body-enable-agent-main

Testing the Flocker Plugin for Docker
=====================================

Once installed, the example provided below runs two simple Docker tests to verify that the plugin is working correctly with the Flocker agents.

#. Run the following command, which uses the Flocker plugin for Docker as the volume driver to create a named volume called ``apples``:

   .. prompt:: bash $

      docker run -v apples:/data --volume-driver flocker busybox sh -c "echo hello > /data/file.txt"

#. Run the following command to reattach the same volume from the first container, and verify that the data (``hello``) has been preserved.

   .. prompt:: bash $

      docker run -v apples:/data --volume-driver flocker busybox sh -c "cat /data/file.txt"

.. include:: ../installation/enabling-agent-service.rst
   :start-after: .. begin-body-enable-agent-nextsteps
   :end-before: .. end-body-enable-agent-nextsteps
