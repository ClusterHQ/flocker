==============
Exposing Ports
==============

.. This section is tested in flocker.acceptance.test_ports.PortsTests.
   Reflect any relevant changes here in those tests.

Each application running in a Docker container has its own isolated networking stack.
To communicate with an application running inside the container we need to forward traffic from a network port in the node where the container is located to the appropriate port within the container.
Flocker takes this one step further: an application is reachable on all nodes in the cluster, no matter where it is currently located.

Let's start a MongoDB container that exposes the database to the external world.

:download:`port-application.yml`

.. literalinclude:: port-application.yml
   :language: yaml

:download:`port-deployment.yml`

.. literalinclude:: port-deployment.yml
   :language: yaml

We will once again run these configuration files with ``flocker-deploy``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy 172.16.255.250 port-deployment.yml port-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    clusterhq/mongodb:latest   mongod     2 seconds ago   Up 1 seconds   27017/tcp, 28017/tcp   mongodb-port-example
   alice@mercury:~/flocker-tutorial$

This time we can communicate with the MongoDB application by connecting to the node where it is running.
Using the ``mongo`` command line tool we will insert an item into a database and check that it can be found.
You should try to follow along and do these database inserts as well.

.. note:: To keep your download for the tutorial as speedy as possible, we've bundled the latest development release of MongoDB in to a micro-sized Docker image.
          *You should not use this image for production.*

If you get a connection refused error try again after a few seconds; the application might take some time to fully start up.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ $ mongo 172.16.255.250
   MongoDB shell version: 2.4.9
   connecting to: 172.16.255.250/test
   > use example;
   switched to db example
   > db.records.insert({"flocker": "tested"})
   > db.records.find({})
   { "_id" : ObjectId("53c958e8e571d2046d9b9df9"), "flocker" : "tested" }

We can also connect to the other node where it isn't running and the traffic will get routed to the correct node:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ mongo 172.16.255.251
   MongoDB shell version: 2.4.9
   connecting to: 172.16.255.251/test
   > use example;
   switched to db example
   > db.records.find({})
   { "_id" : ObjectId("53c958e8e571d2046d9b9df9"), "flocker" : "tested" }

Since the application is transparently accessible from both nodes you can configure a DNS record that points at both IPs and access the application regardless of its location.
See :ref:`routing` for more details.

At this point you have successfully deployed a MongoDB server and communicated with it.
You've also seen how external users don't need to worry about applications' location within the cluster.
In the next section of the tutorial you'll learn how to ensure that the application's data moves along with it, the final step to running stateful applications on a cluster.
