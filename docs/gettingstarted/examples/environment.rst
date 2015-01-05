:tocdepth: 1

===========================
Using Environment Variables
===========================

.. This section is tested in flocker.acceptance.test_environment_variables.EnvironmentVariableTests.
   Reflect any relevant changes here in those tests.

MySQL Example
=============

Flocker supports passing environment variables to a container via its :doc:`Application Configuration <../../advanced/configuration>`.
This example will use a configured environment variable to set the root user password for a MySQL service running inside a container.

Create the Virtual Machines
===========================

You can reuse the Virtual Machines defined in the Vagrant configuration for :doc:`the MongoDB tutorial <../tutorial/index>`.
If you have since shutdown or destroyed those VMs, boot them up again:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ vagrant up
   Bringing machine 'node1' up with 'virtualbox' provider...
   ==> node1: Importing base box 'clusterhq/flocker-dev'...

Launch MySQL
============

Download and save the following configuration files to the ``flocker-tutorial`` directory:

.. note::

   The ``mysql:5.6.17`` Docker image is used in this example for compatibility with ZFS.
   Newer versions of the MySQL Docker image enable asynchronous I/O, which is not yet supported by ZFS on Linux.

:download:`mysql-application.yml`

.. literalinclude:: mysql-application.yml
   :language: yaml

:download:`mysql-deployment.yml`

.. literalinclude:: mysql-deployment.yml
   :language: yaml

Now run ``flocker-deploy`` to deploy the MySQL application to the target Virtual Machine.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy mysql-deployment.yml mysql-application.yml
   alice@mercury:~/flocker-tutorial$

Connect to MySQL & Insert Sample Data
=====================================

You can now use the ``mysql`` client on the host machine to connect to the MySQL server running inside the container.
Connect using the client to the IP address of the Virtual Machine. In this case the example has exposed the default MySQL port 3306 so it is not required to specify a connection port on the command line:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ mysql -h172.16.255.250 -uroot -pclusterhq

   Welcome to the MySQL monitor.  Commands end with ; or \g.
   ...
   mysql> CREATE DATABASE example;
   Query OK, 1 row affected (0.00 sec)

   mysql> USE example;
   Database changed
   mysql> CREATE TABLE `testtable` (`id` INT NOT NULL AUTO_INCREMENT,`name` VARCHAR(45) NULL,PRIMARY KEY (`id`)) ENGINE = MyISAM;
   Query OK, 0 rows affected (0.05 sec)

   mysql> INSERT INTO `testtable` VALUES('','flocker test');
   Query OK, 1 row affected, 1 warning (0.01 sec)

   mysql> quit
   Bye

   alice@mercury:~/flocker-tutorial$


Create a New Deployment Configuration and Move the Application
==============================================================

Download and save the following configuration file to your ``flocker-tutorial`` directory:

:download:`mysql-deployment-moved.yml`

.. literalinclude:: mysql-deployment-moved.yml
   :language: yaml

Then run ``flocker-deploy`` to move the MySQL application along with its data to the new destination host:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy mysql-deployment-moved.yml mysql-application.yml
   alice@mercury:~/flocker-tutorial$

Verify Data Has Moved
=====================

Confirm the application has moved to the target Virtual Machine:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.251 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   51b5b09a46bb        mysql:5.6.17   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:3306->3306/tcp   mysql-volume-example
   alice@mercury:~/flocker-tutorial$

And is no longer running on the original host:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   alice@mercury:~/flocker-tutorial$

You can now connect to MySQL on its host and confirm the sample data has also moved:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ mysql -h172.16.255.251 -uroot -pclusterhq

   Welcome to the MySQL monitor.  Commands end with ; or \g.
   ...
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

This concludes the MySQL example.
