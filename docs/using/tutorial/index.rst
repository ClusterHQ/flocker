.. _tutmongo:

=========================================
Tutorial: Deploying and Migrating MongoDB
=========================================

The goal of this tutorial is to teach you to use Flocker's container, network, and volume orchestration functionality.
By the time you reach the end of the tutorial you will know how to use Flocker to create an application.
You will also know how to expose that application to the network and how to move it from one host to another.
Finally you will know how to configure a persistent data volume for that application.

This tutorial is based around the setup of a MongoDB service.
Flocker is a generic container manager.
MongoDB is used only as an example here.
Any application you can deploy into Docker you can manage with Flocker.

If you have any feedback or problems, you can :ref:`talk-to-us`.

.. toctree::
   :maxdepth: 2

   vagrant-setup
   moving-applications
   exposing-ports
   volumes
