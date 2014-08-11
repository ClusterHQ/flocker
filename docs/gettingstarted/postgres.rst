===========================
Example: Running PostgreSQL
===========================

Once you've successfully followed through :doc:`./tutorial/index` this example will show you how to deploy a PostgreSQL container with Flocker.
We'll insert some data, then use ``flocker-deploy`` to move the PostgreSQL server container to another virtual machine.
Our data will be carried over along with the application.

Create the virtual machines
===========================

We'll be using the same Vagrant configuration as :doc:`the MongoDB tutorial <./tutorial/index>`.
If you haven't already started up the Vagrant virtual machines follow the :doc:`setup instructions <./tutorial/vagrant-setup>`.

Download the PostgreSQL image
=============================

The ``postgres`` image is quite big, so you may wish to pre-fetch it to your nodes so you don't have to wait for downloads half-way through this example.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.250 docker pull postgres
   ...
   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.251 docker pull postgres
   ...
   alice@mercury:~/flocker-postgres$

Launch the PostgreSQL server
============================

Download and save the following configuration files to your ``flocker-postgres`` directory:

:download:`postgres-application.yml`

.. literalinclude:: postgres-application.yml
   :language: yaml

:download:`postgres-deployment.yml`

.. literalinclude:: postgres-deployment.yml
   :language: yaml

As you can see, we will be pulling the ``postgres`` image and deploying to one of our virtual nodes.
Run ``flocker-deploy`` to download the image and get the container running:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ flocker-deploy postgres-deployment.yml postgres-application.yml
   alice@mercury:~/flocker-postgres$

You can keep running ``ssh root@172.16.255.250 docker ps`` until you see the container running:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   f6ee0fbd0446        postgres:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   postgres-volume-example


Connect to the PostgreSQL server
================================

We can now use the ``psql`` client on our host machine (you will need to install this if you do not already have it) to connect to the PostgreSQL server running inside the container.
Connect using the client to the IP address of our virtual machine, using the port number we exposed in our application config.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ psql postgres --host 172.16.255.250 --port 5432 --username postgres
   psql (9.3.5)
   Type "help" for help.

   postgres=#

Create a new database and insert some data
==========================================

Now we have a connection, we'll create a new database with the simplest possible structure; a single table with one integer column.
We'll then switch our connection to use the new database and insert a row. From the running psql client shell:

.. code-block:: console

   postgres=# \list
                                List of databases
      Name    |  Owner   | Encoding  | Collate | Ctype |   Access privileges   
   -----------+----------+-----------+---------+-------+-----------------------
    postgres  | postgres | SQL_ASCII | C       | C     | 
    template0 | postgres | SQL_ASCII | C       | C     | =c/postgres          +
              |          |           |         |       | postgres=CTc/postgres
    template1 | postgres | SQL_ASCII | C       | C     | =c/postgres          +
              |          |           |         |       | postgres=CTc/postgres
   (3 rows)
   
   postgres=# CREATE DATABASE flockertest;
   CREATE DATABASE
   postgres=# \list
                                 List of databases
       Name     |  Owner   | Encoding  | Collate | Ctype |   Access privileges   
   -------------+----------+-----------+---------+-------+-----------------------
    flockertest | postgres | SQL_ASCII | C       | C     | 
    postgres    | postgres | SQL_ASCII | C       | C     | 
    template0   | postgres | SQL_ASCII | C       | C     | =c/postgres          +
                |          |           |         |       | postgres=CTc/postgres
    template1   | postgres | SQL_ASCII | C       | C     | =c/postgres          +
                |          |           |         |       | postgres=CTc/postgres
   (4 rows)
   
   postgres=# \c flockertest;
   psql (9.3.5, server 9.2.4)
   You are now connected to database "flockertest" as user "postgres".
   flockertest=# CREATE TABLE testtable (testcolumn int); 
   CREATE TABLE
   flockertest=# insert into testtable (testcolumn) values (3);
   INSERT 0 1
   flockertest=# select * from testtable;
    testcolumn 
   ------------
             3
   (1 row)
   
   flockertest=# \q

Our last command ``\q`` quits the client.

Create a new deployment config and move the application
=======================================================

Download the new deployment configuration and save to your ``flocker-postgres`` directory.

:download:`postgres-deployment-moved.yml`

.. literalinclude:: postgres-deployment-moved.yml
   :language: yaml

Now run ``flocker-deploy`` on the new config:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ flocker-deploy postgres-deployment-moved.yml postgres-application.yml
   alice@mercury:~/flocker-postgres$

You can keep running ``ssh root@172.16.255.251 docker ps`` until you see the container running:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   f6ee0fbd0446        postgres:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   postgres-volume-example


Connect via client and verify data has moved
============================================

We can now connect to the newly moved database and see that the data was moved to the new location.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ psql postgres --host 172.16.255.251 --port 5432 --username postgres
   Password for user postgres:
   psql (9.3.5, server 9.2.4)
   Type "help" for help.

   postgres=# \c flockertest;
   psql (9.3.5, server 9.2.4)
   You are now connected to database "flockertest" as user "postgres".
   flockertest=# CREATE TABLE testtable (testcolumn int); 
   CREATE TABLE
   flockertest=# insert into testtable (testcolumn) values (3);
   INSERT 0 1
   flockertest=# select * from testtable;
    testcolumn 
   ------------
             3
   (1 row)
