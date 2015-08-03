
=============
Using Flocker
=============

Flocker is a lightweight volume and container manager.
It lets you:

* Define your application as a set of connected Docker containers
* Deploy them to one or multiple hosts
* Easily migrate them along with their data between hosts

The goal of Flocker is to simplify the operational tasks that come along with running databases, key-value stores, queues and other data-backed services in containers.
This Getting Started guide will walk you step-by-step through installing Flocker and provide some tutorials that demonstrate the essential features of Flocker.

.. warning::
   It is important to remember that your firewall will need to allow access to the ports your applications are exposing.

   Keep in mind the consequences of exposing unsecured services to the Internet.
   Both applications with exposed ports and applications accessed via links will be accessible by anyone on the Internet.

.. toctree::
   :maxdepth: 2

   config/index
   administering/index
   tutorial/index
   examples/apps
   examples/features
