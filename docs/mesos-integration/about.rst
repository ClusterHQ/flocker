.. _about-mesos-integration:

======================
About This Integration
======================

Flocker works with Mesos via two different integration paths.

* With the `Mesos-Flocker Isolator <http://flocker.mesosframeworks.com/>`_ to provide storage to any Mesos framework and any application, whether Dockerized or not.
  Currently experimental.
* With Marathon and Flocker Plugin for Docker to provide storage to Dockerized applications running on Marathon.
  `See our blog post for details <https://clusterhq.com/2015/10/06/marathon-ha-demo/>`_.

.. _concepts-mesos-integration:

Concepts
========

Flocker Volumes
---------------

Flocker volumes represent actual underlying storage, typically allocated from IaaS block device provider, such as EBS.
They have names, sizes, profiles and metadata.
