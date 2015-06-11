============
Data Volumes
============

The Problem
===========

By default moving an application from one node to another does not move its data along with it.
Before proceeding let's see in more detail what the problem is by continuing the :doc:`Exposing Ports <exposing-ports>` example.

Recall that we inserted some data into the database.
Next we'll use a new configuration file that moves the application to a different node.

:download:`port-deployment-moved.yml`

.. literalinclude:: port-deployment-moved.yml
   :language: yaml

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy 172.16.255.250 port-deployment-moved.yml port-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.251 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    clusterhq/mongodb:latest   mongod     2 seconds ago   Up 1 seconds   27017/tcp, 28017/tcp   mongodb-port-example
   alice@mercury:~/flocker-tutorial$

If we query the database the records we've previously inserted have disappeared!
The application has moved but the data has been left behind.

.. code-block:: console

    alice@mercury:~/flocker-tutorial$ mongo 172.16.255.251
    MongoDB shell version: 2.4.9
    connecting to: 172.16.255.251/test
    > use example;
    switched to db example
    > db.records.find({})
    >

The Solution
============

Unlike many other Docker frameworks Flocker has a solution for this problem, a data volume manager.
An application with a Flocker volume configured will move the data along with the application, transparently and with no additional intervention on your part.

We'll create a new configuration for the cluster, this time adding a volume to the MongoDB container.

:download:`volume-application.yml`

.. literalinclude:: volume-application.yml
   :language: yaml

:download:`volume-deployment.yml`

.. literalinclude:: volume-deployment.yml
   :language: yaml

Then we'll run these configuration files with ``flocker-deploy``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy 172.16.255.250 volume-deployment.yml volume-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    clusterhq/mongodb:latest   mongod     2 seconds ago   Up 1 seconds   27017/tcp, 28017/tcp   mongodb-volume-example
   alice@mercury:~/flocker-tutorial$

Once again we'll insert some data into the database:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ $ mongo 172.16.255.250
   MongoDB shell version: 2.4.9
   connecting to: 172.16.255.250/test
   > use example;
   switched to db example
   > db.records.insert({"the data": "it moves"})
   > db.records.find({})
   { "_id" : ObjectId("53d80b08a3ad4df94a2a72d6"), "the data" : "it moves" }

Next we'll move the application to the other node.

:download:`volume-deployment-moved.yml`

.. literalinclude:: volume-deployment-moved.yml
   :language: yaml

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy 172.16.255.250 volume-deployment-moved.yml volume-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.251 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    clusterhq/mongodb:latest   mongod     2 seconds ago   Up 1 seconds   27017/tcp, 28017/tcp   mongodb-volume-example
   alice@mercury:~/flocker-tutorial$

This time however the data has moved with the application:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ mongo 172.16.255.251
   MongoDB shell version: 2.4.9
   connecting to: 172.16.255.251/test
   > use example;
   switched to db example
   > db.records.find({})
   { "_id" : ObjectId("53d80b08a3ad4df94a2a72d6"), "the data" : "it moves" }

At this point you have successfully deployed a MongoDB server and communicated with it.
You've also seen how Flocker allows you to move an application's data to different locations in a cluster as the application is moved.
You now know how to run stateful applications in a Docker cluster using Flocker.

The virtual machines you are running will be useful for testing Flocker and running other examples in the documentation.
If you would like to shut them down temporarily you can run ``vagrant halt`` in the tutorial directory.
You can then restart them by running ``vagrant up``.
If you would like to completely remove the virtual machines you can run ``vagrant destroy``.
