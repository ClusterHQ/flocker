:tocdepth: 2

============================
Flocker Application Examples
============================

Once you've successfully followed :doc:`../tutorial/index`, you may wish to test some common application use cases or explore some of Flocker's features in more detail.
We've included a small library of examples below, with Flocker application and deployment configurations you can download, test and play around with.

How to Use the Examples
=======================

Creating the Virtual Machines
-----------------------------

For convenience, all examples below include deployment configuration files that can be used to test against the Virtual Machines created in the MongoDB tutorial.
If you haven't already started up the Vagrant Virtual Machines, follow the :ref:`setup instructions <VagrantSetup>` to get started.

Moving Your Applications
------------------------

Each of the examples in the library include two deployment configuration files.
These allow you to explore how Flocker moves stateful components of your application (data volumes) when you move a container to another node.
You should use these deployment files to first deploy your application to one node with ``flocker-deploy``, then use the application to create some stateful data inside your container, then finally run ``flocker-deploy`` again on the other deployment file to test your migration.

For example:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy deployment.yml application.yml
   ...
   <use your application, save some data>
   ...
   alice@mercury:~/flocker-tutorial$ flocker-deploy deployment-moved.yml application.yml

Examples of creating state are included in each of the examples below.  

Flocker Advanced Feature Examples
=================================

.. toctree::
   :maxdepth: 2

   environment
   linking

Flocker Application Examples
============================

.. toctree::
   :maxdepth: 2

   PostgreSQL <postgres>
   MySQL <environment>
   Elasticsearch, Logstash & Kibana stack <linking>
      
