.. _about-kubernetes-integration:

======================
About This Integration
======================

Kubernetes 1.1 and later has native support for Flocker volumes.

See `Kubernetes Flocker docs <https://docs.clusterhq.com/en/latest/labs/volumes-cli.html>`_ for more details and example usage.

.. _concepts-kubernetes-integration:

Concepts
========

Flocker Volumes
---------------

Flocker volumes represent actual underlying storage, typically allocated from IaaS block device provider, such as EBS.
They have names, sizes, profiles and metadata.
