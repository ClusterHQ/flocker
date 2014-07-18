==============
Exposing Ports
==============

Exposing Application Ports
==========================

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

Notice that this time we mention the node that has no applications deployed on it.
This will ensure that ``flocker-deploy`` knows that it exists.
We will once again run these configuration files with ``flocker-deploy``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy port-deployment.yml port-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    dockerfile/mongodb:latest   mongod     2 seconds ago   Up 1 seconds   27017/tcp, 28017/tcp   mongodb-port-example
   alice@mercury:~/flocker-tutorial$

This time we can communicate with the MongoDB application by connecting to the node where it is running:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ $ mongo 172.16.255.250
   MongoDB shell version: 2.4.9
   connecting to: 172.16.255.250/test
   > use example;
   switched to db example
   > db.records.insert({"flocker": "tested"})
   > db.records.find({})
   { "_id" : ObjectId("53c958e8e571d2046d9b9df9"), "flocker" : "tested" }

We can also connect to the other node where it isn't running and the traffic will get to correct node:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ mongo 172.16.255.251
   MongoDB shell version: 2.4.9
   connecting to: 172.16.255.251/test
   > use example;
   switched to db example
   > db.records.find({})
   { "_id" : ObjectId("53c958e8e571d2046d9b9df9"), "flocker" : "tested" }

Since the node is transparently accessible from both nodes you can configure a DNS record that points at both IPs and access the application regardless of its location.
See :doc:`../routing/index` for more details.
