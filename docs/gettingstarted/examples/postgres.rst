:tocdepth: 1

===========================
Example: Running PostgreSQL
===========================

Download the Docker Image
=========================

The official ``postgres`` Docker image is quite big, so you may wish to pull it to your nodes so you don't have to wait for downloads half-way through this example.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh -t root@172.16.255.250 docker pull postgres
   ...
   alice@mercury:~/flocker-postgres$ ssh -t root@172.16.255.251 docker pull postgres


Launch PostgreSQL
=================

Download and save the following configuration files to your ``flocker-postgres`` directory:

:download:`postgres-application.yml`

.. literalinclude:: postgres-application.yml
   :language: yaml

:download:`postgres-deployment.yml`

.. literalinclude:: postgres-deployment.yml
   :language: yaml

.. code-block:: console

   alice@mercury:~/flocker-postgres$ flocker-deploy postgres-deployment.yml postgres-application.yml
   alice@mercury:~/flocker-postgres$

Connect to PostgreSQL
=====================

We can now use the ``psql`` client on our host machine to connect to the PostgreSQL server running inside the container.
Connect using the client to the IP address of our virtual machine, using the port number we exposed in our application configuration.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ psql postgres --host 172.16.255.250 --port 5432 --username postgres
   psql (9.3.5)
   Type "help" for help.

   postgres=#


Insert a Row in the Database
============================

.. code-block:: console
 
   postgres=# CREATE DATABASE flockertest;
   CREATE DATABASE
   postgres=# \connect flockertest;
   psql (9.3.5)
   You are now connected to database "flockertest" as user "postgres".
   flockertest=# CREATE TABLE testtable (testcolumn int); 
   CREATE TABLE
   flockertest=# INSERT INTO testtable (testcolumn) VALUES (3);
   INSERT 0 1
   flockertest=# SELECT * FROM testtable;
    testcolumn 
   ------------
             3
   (1 row)
   
   flockertest=# \quit


Move the Application
====================

:download:`postgres-deployment-moved.yml`

.. literalinclude:: postgres-deployment-moved.yml
   :language: yaml

.. code-block:: console

   alice@mercury:~/flocker-postgres$ flocker-deploy postgres-deployment-moved.yml postgres-application.yml
   alice@mercury:~/flocker-postgres$

Verify Data Has Moved
=====================

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

