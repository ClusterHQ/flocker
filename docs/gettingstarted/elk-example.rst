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


Create the Virtual Machines
===========================

We'll use the same Vagrant environment as :doc:`the MongoDB tutorial <./tutorial/index>`.
If you haven't already started up the Vagrant virtual machines follow the :doc:`setup instructions <./tutorial/vagrant-setup>`.


Download the Docker Images
==========================

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh --tty root@172.16.255.250 docker pull tomprince/test-elasticsearch
   alice@mercury:~/flocker-elk$ ssh --tty root@172.16.255.250 docker pull tomprince/test-logstash
   alice@mercury:~/flocker-elk$ ssh --tty root@172.16.255.250 docker pull tomprince/test-kibana
   ...
   alice@mercury:~/flocker-elk$ ssh --tty root@172.16.255.251 docker pull tomprince/test-elasticsearch
   alice@mercury:~/flocker-elk$ ssh --tty root@172.16.255.251 docker pull tomprince/test-logstash
   alice@mercury:~/flocker-elk$ ssh --tty root@172.16.255.251 docker pull tomprince/test-kibana
   ...
   alice@mercury:~/flocker-elk$

.. note:: We use the ``--tty`` option to ``ssh`` so that progress is displayed.
          If you omit it the pull will still work but you may not get any output for a long time.


Deploy on Node1
===============

Download and save the following configuration files to your ``flocker-tutorial`` directory:

:download:`elk-application.yml`

.. literalinclude:: elk-application.yml
   :language: yaml

:download:`elk-deployment.yml`

.. literalinclude:: elk-deployment.yml
   :language: yaml

Run ``flocker-deploy`` to start the three applications:

.. code-block:: console

   alice@mercury:~/flocker-elk$ flocker-deploy elk-deployment.yml elk-application.yml
   alice@mercury:~/flocker-elk$

All three applications should now be running in separate containers on node1.
You can verify that by running ``docker ps``:

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh root@172.16.255.250 docker ps
   alice@mercury:~/flocker-elk$

Connect to Kibana
=================

Browse to port 80 on node1 with your web browser.
You should see the Kibana web interface.
There won't be any messages yet.

XXX: Insert screenshot.

Generate Log Messages
=====================

For this tutorial, Logstash has been configured to accept JSON encoded messages on port 5000.
Use ``telnet`` to connect to port 5000.
Type some JSON formatted messages.
For example:

.. code-block:: console

   alice@mercury:~/flocker-elk$ telnet ssh 172.16.255.250 5000

   ...
   alice@mercury:~/flocker-elk$

Now refresh the Kibana web interface and you should see those messages.

XXX: Insert screenshot.

Move ElasticSearch to node2
===========================

Edit the ``elk-deployment.yml`` file so that ElasticSearch is on node2.
It should now look like:

.. literalinclude:: elk-deployment-moved.yml
   :language: yaml

Now run ``flocker-deploy`` with the new configuration:

.. code-block:: console

   alice@mercury:~/flocker-elk$ flocker-deploy elk-deployment.yml elk-application.yml
   alice@mercury:~/flocker-elk$

Now we'll verify that the ElasticSearch application has moved to the other VM:

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh root@172.16.255.251 docker ps
   XXX: insert output

And is no longer running on the original host:

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   XXX: Insert output
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
