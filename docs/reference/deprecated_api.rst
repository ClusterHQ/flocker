.. _deprecated-endpoints:

====================
Deprecated Endpoints
====================

.. XXX: As part of FLOC 3518 the Container API Endpoints below have been deprecated, as Flocker is not a container framework:

.. warning:: 
   The endpoints listed in this document are deprecated, and they will not be available in future versions of the Flocker API.

The Flocker Container API
=========================

The Flocker Container API enables you to manage containers in your cluster.
However, ClusterHQ is no longer developing any future features in this area, as you can now use Flocker with 3rd party orchestration tools.

.. note::
   Flocker's container management features depend on Docker.
   You will need to make sure `Docker (at least 1.8) is installed`_ and running before you enable ``flocker-container-agent``.

.. _Docker (at least 1.8) is installed: https://docs.docker.com/installation/

Enabling the Container Agent Service
------------------------------------

* On CentOS 7 and RHEL 7.2, run the following commands:
  
  .. prompt:: bash [root@agent-node]#
  
     systemctl enable flocker-container-agent
     systemctl start flocker-container-agent

* On Ubuntu, run the following command:

  .. prompt:: bash [root@agent-node]#
  
     service flocker-container-agent start

Deprecated Endpoints
====================

The deprecated endpoints listed below are still available for use, but please be aware that they will not be available in future versions of the Flocker API:

.. contents::
        :local:

.. autoklein:: flocker.control.httpapi.ConfigurationAPIUserV1
       :schema_store_fqpn: flocker.control.httpapi.SCHEMAS
       :prefix: /v1
       :examples_path: api_examples.yml
       :section: container
