===========================
Example: Linking Containers
===========================

In this example you will learn how to deploy ElasticSearch, Logstash, and Kibana with Flocker.
This example demonstrates how applications running in separate Docker containers can be linked together, so that they can connect to one another, even when they are deployed on separate nodes.

The three applications are connected as follows:
* Logstash receives logged messages and relays them to ElasticSearch.
* ElasticSearch stores the logged messages in a database.
* Kibana connects to ElasticSearch to retrieve the logged messages and presents them in a web interface.

We'll start by deploying all three applications on node1.
Then we'll generate some log messages and view them in the Kibana web interface.
Then we'll use ``flocker-deploy`` to move the ElasticSearch container to the second node.
The ElasticSearch data will be moved with the application.
The Logstash and Kibana applications will now connect to ElasticSearch on node2.

The requirements are the same as the MongoDB tutorial.


Create the Virtual Machines
===========================

We'll be using the same Vagrant configuration as :doc:`the MongoDB tutorial <./tutorial/index>`.
If you haven't already started up the Vagrant virtual machines follow the :doc:`setup instructions <./tutorial/vagrant-setup>`.


Download the Docker Images
==========================

(We use the ``-t`` option to ``ssh`` so that progress is displayed; if you omit it the pull will still work but you may not get any output for a long time.)

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh -t root@172.16.255.250 docker pull tomprince/test-elasticsearch
   alice@mercury:~/flocker-elk$ ssh -t root@172.16.255.250 docker pull tomprince/test-logstash
   alice@mercury:~/flocker-elk$ ssh -t root@172.16.255.250 docker pull tomprince/test-kibana
   ...
   # XXX This gets tedious to repeat all three on the second node, perhaps we
   # need a script to do the pre-caching or perhaps we only use one node for this
   # example.
   alice@mercury:~/flocker-elk$ ssh -t root@172.16.255.251 docker pull ...
   ...
   alice@mercury:~/flocker-elk$


Launch XXX
==========

Download and save the following configuration files to your ``flocker-postgres`` directory:

:download:`elk-application.yml`

.. literalinclude:: elk-application.yml
   :language: yaml

:download:`elk-deployment.yml`

.. literalinclude:: elk-deployment.yml
   :language: yaml

Run ``flocker-deploy`` to download the images and get the container running:

.. code-block:: console

   alice@mercury:~/flocker-elk$ flocker-deploy elk-deployment.yml elk-application.yml
   alice@mercury:~/flocker-elk$

You can keep running ``ssh root@172.16.255.250 docker ps`` until you see the container running:

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   f6ee0fbd0446        XXX:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   XXX-XXX-XXX
   alice@mercury:~/flocker-elk$

Connect to XXX
==============

Connect to the IP address of our virtual machine, using the port number we exposed in our application configuration.

.. code-block:: console

   alice@mercury:~/flocker-elk$ XXX
   > XXX
   > exit
   alice@mercury:~/flocker-elk$


Add some data
=============

XXX


Create a New Deployment Configuration and Move the Application
==============================================================

Download the new deployment configuration and save to your ``flocker-elk`` directory.

:download:`elk-deployment-moved.yml`

.. literalinclude:: elk-deployment-moved.yml
   :language: yaml

Now run ``flocker-deploy`` on the new configuration:

.. code-block:: console

   alice@mercury:~/flocker-elk$ flocker-deploy elk-deployment-moved.yml elk-application.yml
   alice@mercury:~/flocker-elk$

Now we'll verify that our application has moved to the other VM:

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh root@172.16.255.251 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   51b5b09a46bb        clusterhq/XXX:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   XXX
   alice@mercury:~/flocker-postgres$

And is no longer running on the original host:

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   alice@mercury:~/flocker-elk$

Verify Our Data Has Moved with the Application
==============================================

Query the ``flockertest`` database for the data we previously inserted.
You will find that Flocker has moved our volume with the container and our data has been preserved.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ psql postgres --host 172.16.255.251 --port 5432 --username postgres
   psql (9.3.5)
   Type "help" for help.

   postgres=# \connect flockertest;
   psql (9.3.5)
   You are now connected to database "flockertest" as user "postgres".
   flockertest=# select * from testtable;
    testcolumn
   ------------
             3
   (1 row)

This concludes our example for using Flocker with PostgreSQL.
Now you've successfully followed through both our tutorial and a further working example of what you can do with flocker, you may now wish to read through the :doc:`../advanced/index`.

.. _`PostgreSQL`: https://www.postgresql.org/download/
