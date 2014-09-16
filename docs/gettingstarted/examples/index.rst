:tocdepth: 2

================
Further Examples
================

Once you've successfully followed through :doc:`../tutorial/index`, you may wish to explore some of Flocker's features in more detail.
We've included a small library of examples below, with Flocker application and deployment configs you can download, test and play around with.

How to Use the Examples
=======================

Creating the Virtual Machines
-----------------------------

For convenience, all examples below include deployment config files that can be used to test against the Virtual Machines created in the main tutorial.
If you haven't already started up the Vagrant virtual machines, follow the :ref:`setup instructions <VagrantSetup>` to get started.

Moving Your Applications
------------------------

Each of the examples in the library include two deployment config files.
These allow you to explore how Flocker moves stateful components of your application (data volumes) when you move a container to another node.
You should use these deployment files to first deploy your application to one node with ``flocker-deploy``, then use the application to create some stateful data inside your container, then finally run ``flocker-deploy`` again on the other deployment file to test your migration.

For example:

.. code-block:: console

   alice@mercury:~/flocker-mysql$ flocker-deploy mysql-deployment.yml mysql-application.yml
   alice@mercury:~/flocker-mysql$ mysql -h172.16.255.250 -uroot -pclusterhq
   Welcome to the MySQL monitor.  Commands end with ; or \g.
   ...
   CREATE TABLE ...
   INSERT INTO ...
   ...
   alice@mercury:~/flocker-mysql$ flocker-deploy mysql-deployment-moved.yml mysql-application.yml
   alice@mercury:~/flocker-mysql$ mysql -h172.16.255.251 -uroot -pclusterhq
   Welcome to the MySQL monitor.  Commands end with ; or \g.
   ...
   SELECT * FROM ...

Examples of creating state are included in each of the examples below.  

Flocker Examples Library
========================

.. toctree::
   :maxdepth: 2

   postgres
   environment
   linking
   
