==================================================================
Supported Operating Systems, Cloud Providers, and Storage Backends
==================================================================

.. _supported-operating-systems:

Supported Operating Systems
===========================

* CentOS 7
* Ubuntu 14.04
* Ubuntu 15.04 (Command Line only)
* OS X (Command Line only)


Supported Cloud Providers
=========================

* AWS
* Rackspace

.. _storage-backends:

List of Storage Backends
========================

The following backends can be used with Flocker:

* AWS EBS
* Rackspace Cloud Block Storage
* Anything that supports the OpenStack Cinder API
* EMC ScaleIO
* EMC XtremIO
* VMware
* NetApp OnTap
* Hedvig
* ConvergeIO
* Saratoga Speed
* Local storage using our ZFS driver (currently Experimental)

Configuration details for each of the backends can be found in the :ref:`Configuring the Nodes and Storage Backends<agent-yml>` topic.

.. XXX FLOC 3144 - add a link here to the instructions on how to create your own backend driver

.. XXX add link to 3rd party orchestration docs. See FLOC 2229
