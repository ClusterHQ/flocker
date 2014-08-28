======================
Example: Running MySQL
======================

Once you've successfully followed through :doc:`./tutorial/index` this example will show you how to deploy a MySQL container with Flocker.
We'll insert some data, then use ``flocker-deploy`` to move the MySQL server container to another virtual machine.
The data in the database will be moved along with the application.


Create the Virtual Machines
===========================

We'll be re-using the virtual machines defined in the Vagrant configuration for :doc:`the MongoDB tutorial <./tutorial/index>`.
If you have since shutdown or destroyed those VMs, boot them up again:

.. code-block:: console

   alice@mercury:~/flocker-mysql$ vagrant up
   Bringing machine 'node1' up with 'virtualbox' provider...
   ==> node1: Importing base box 'clusterhq/flocker-dev'...


Download the Docker Image
=========================

The Docker image we'll be using is quite large, so you should pre-fetch it to your nodes.

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh -t root@172.16.255.250 docker pull mysql:5.6.17
   ...
   alice@mercury:~/flocker-mysql$ ssh -t root@172.16.255.251 docker pull mysql:5.6.17
   ...
   alice@mercury:~/flocker-mysql$

These commands may take several minutes to complete, depending on your hardware and the speed of your internet connection.

.. note::

   We use the mysql:5.6.17 docker image in this tutorial for compatibility with ZFS.
   Newer versions of the MySQL docker image enable asynchronous I/O, which is not yet supported by ZFS on Linux.


Launch MySQL
============

Download and save the following configuration files to the ``flocker-mysql`` directory:

:download:`mysql-application.yml`

.. literalinclude:: mysql-application.yml
   :language: yaml

:download:`mysql-deployment.yml`

.. literalinclude:: mysql-deployment.yml
   :language: yaml

This is an example where we map MySQL's default port 3306 in the container to 3306 on the host and specify the volume mountpoint in the container where the data is stored.
We will be using the ``mysql`` image and deploying to one of the virtual nodes.
Run ``flocker-deploy`` to instantiate the container on its specified host:

.. code-block:: console

   alice@mercury:~/flocker-mysql$ flocker-deploy mysql-deployment.yml mysql-application.yml
   alice@mercury:~/flocker-mysql$

Run ``ssh root@172.16.255.250 docker ps`` and you should see the container running:

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   f6ee0fbd0446        mysql:5.6.17   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:3306->3306/tcp   mysql-volume-example

.. note::
   
   It can take a few moments after ``flocker-deploy`` completes for the container to appear here.
   If you don't see it immediately, keep running the ``docker ps`` command until you have output similar to the above.

Connect to MySQL
================

We can now use the ``mysql`` client on the host machine (you will need to install this if you do not already have it) to connect to the MySQL server running inside the container.
Connect using the client to the IP address of the virtual machine, using the port number we exposed in the application config.
Our example MySQL image sets the ``root`` user password to ``clusterhq`` so we'll connect to MySQL using those credentials and specify the IP address of the virtual machine as the host.

.. code-block:: console

   alice@mercury:~/flocker-mysql$ mysql -h172.16.255.250 -uroot -pclusterhq

   Welcome to the MySQL monitor.  Commands end with ; or \g.
   Your MySQL connection id is 3
   Server version: 5.6.17 Source distribution
   
   Copyright (c) 2000, 2014, Oracle and/or its affiliates. All rights reserved.
   
   Oracle is a registered trademark of Oracle Corporation and/or its
   affiliates. Other names may be trademarks of their respective
   owners.
   
   Type 'help;' or '\h' for help. Type '\c' to clear the current input statement.
   
   mysql> 

Let's have a look at the databases already in the system:

.. code-block:: console

   mysql> SHOW DATABASES;
   +--------------------+
   | Database           |
   +--------------------+
   | information_schema |
   | mysql              |
   | performance_schema |
   +--------------------+
   3 rows in set (0.00 sec)

These are the databases used by MySQL itself and bundled as part of a new installation of the MySQL server.
We'll now create a new database for some test data, create a table and save some data.

.. code-block:: console

   mysql> CREATE DATABASE example;
   Query OK, 1 row affected (0.00 sec)
   
   mysql> USE example;
   Database changed
   mysql> CREATE TABLE `testtable` (`id` INT NOT NULL AUTO_INCREMENT,`name` VARCHAR(45) NULL,PRIMARY KEY (`id`)) ENGINE = MyISAM;
   Query OK, 0 rows affected (0.05 sec)
   
   mysql> INSERT INTO `testtable` VALUES('','flocker test');
   Query OK, 1 row affected, 1 warning (0.01 sec)
   
   mysql> 

Next we'll verify the data has been saved and can be retrieved with a ``SELECT`` query.

.. code-block:: console

   mysql> SELECT * FROM `testtable`;
   +----+--------------+
   | id | name         |
   +----+--------------+
   |  1 | flocker test |
   +----+--------------+
   1 row in set (0.00 sec)
   
   mysql> quit
   Bye

   alice@mercury:~/flocker-mysql$

.. note:: Type in ``quit`` after you've run the ``SELECT`` query to exit the MySQL client.

Create a New Deployment Config and Move the Application
=======================================================

Download the new deployment configuration and save to your ``flocker-mysql`` directory.
This new configuration tells ``flocker-deploy`` to move the container to a different node, by specifying a new IP address to deploy the application with.

:download:`mysql-deployment-moved.yml`

.. literalinclude:: mysql-deployment-moved.yml
   :language: yaml

Now run ``flocker-deploy`` with the new configuration files:

.. code-block:: console

   alice@mercury:~/flocker-mysql$ flocker-deploy mysql-deployment-moved.yml mysql-application.yml
   alice@mercury:~/flocker-mysql$

Now we'll verify that the application has moved to the other VM:

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.251 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   51b5b09a46bb        mysql:5.6.17   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:3306->3306/tcp   mysql-volume-example
   alice@mercury:~/flocker-mysql$

And is no longer running on the original host:

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   alice@mercury:~/flocker-mysql$


Verify the Data Has Moved With the Application
==============================================

We'll now connect to the second node via the MySQL client, using the same authentication credentials as before.

.. code-block:: console

   alice@mercury:~/flocker-mysql$ mysql -h172.16.255.251 -uroot -pclusterhq

   Welcome to the MySQL monitor.  Commands end with ; or \g.
   Your MySQL connection id is 1
   Server version: 5.6.17 Source distribution
   
   Copyright (c) 2000, 2014, Oracle and/or its affiliates. All rights reserved.
   
   Oracle is a registered trademark of Oracle Corporation and/or its
   affiliates. Other names may be trademarks of their respective
   owners.
   
   Type 'help;' or '\h' for help. Type '\c' to clear the current input statement.
   
   mysql>

Now query the ``example`` database for the data we previously inserted.
You will find ``flocker-deploy`` has moved our volume with the container and our data has been preserved.

.. code-block:: console

   mysql> SHOW DATABASES;
   +--------------------+
   | Database           |
   +--------------------+
   | information_schema |
   | example            |
   | mysql              |
   | performance_schema |
   +--------------------+
   4 rows in set (0.02 sec)
   
   mysql> USE example;
   Reading table information for completion of table and column names
   You can turn off this feature to get a quicker startup with -A
   
   Database changed
   mysql> SELECT * FROM `testtable`;
   +----+--------------+
   | id | name         |
   +----+--------------+
   |  1 | flocker test |
   +----+--------------+
   1 row in set (0.01 sec)
   
   mysql>

You can now exit the MySQL client.

---------------------------------

This concludes our example for using Flocker with MySQL.
Now you've successfully followed through both our tutorial and a further working example of what you can do with flocker, you may wish to read through the :doc:`../advanced/index`.
