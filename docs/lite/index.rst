.. _lite:

=========================
Flocker Lite Architecture
=========================

Flocker Docker Plugin
=====================

.. code-block:: sh

   docker volume create \
       --driver flocker \
       --name example-database \
       --opt size=10GiB \
       --opt profile=gold

.. seqdiag:: diagrams/docker-volume-create.diag
