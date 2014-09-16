:tocdepth: 1

====================================
Example: Using Environment Variables
====================================

Download the Docker Image
=========================

The Docker image we'll be using is quite large, so you should pre-fetch it to your nodes.

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh -t root@172.16.255.250 docker pull mysql:5.6.17
   ...
   alice@mercury:~/flocker-mysql$ ssh -t root@172.16.255.251 docker pull mysql:5.6.17

.. note::

   We use the ``mysql:5.6.17`` Docker image in this tutorial for compatibility with ZFS.
   Newer versions of the MySQL Docker image enable asynchronous I/O, which is not yet supported by ZFS on Linux.


Launch MySQL
============

Download and save the following configuration files to the ``flocker-mysql`` directory:

:download:`mysql-application.yml`

.. literalinclude:: mysql-application.yml
   :language: yaml

:download:`mysql-deployment.yml`

.. literalinclude:: mysql-deployment.yml
   :language: yaml

.. code-block:: console

   alice@mercury:~/flocker-mysql$ flocker-deploy mysql-deployment.yml mysql-application.yml
   alice@mercury:~/flocker-mysql$

Connect to MySQL
================

.. code-block:: console

   alice@mercury:~/flocker-mysql$ mysql -h172.16.255.250 -uroot -pclusterhq

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

   alice@mercury:~/flocker-mysql$


Create a New Deployment Configuration and Move the Application
==============================================================

:download:`mysql-deployment-moved.yml`

.. literalinclude:: mysql-deployment-moved.yml
   :language: yaml

.. code-block:: console

   alice@mercury:~/flocker-mysql$ flocker-deploy mysql-deployment-moved.yml mysql-application.yml
   alice@mercury:~/flocker-mysql$

Verify the Data Has Moved
=========================

.. code-block:: console

   alice@mercury:~/flocker-mysql$ mysql -h172.16.255.251 -uroot -pclusterhq

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


