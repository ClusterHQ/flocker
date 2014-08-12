===========================
Example: Running PostgreSQL
===========================

Once you've successfully followed through :doc:`./tutorial/index` this example will show you how to deploy a PostgreSQL container with Flocker.
We'll insert some data, then use ``flocker-deploy`` to move the PostgreSQL server container to another virtual machine.
The data in the database will be moved along with the application.


Create the Virtual Machines
===========================

We'll be using the same Vagrant configuration as :doc:`the MongoDB tutorial <./tutorial/index>`.
If you haven't already started up the Vagrant virtual machines follow the :doc:`setup instructions <./tutorial/vagrant-setup>`.


Download the Docker Image
=========================

The official ``postgres`` Docker image is quite big, so you may wish to pre-fetch it to your nodes so you don't have to wait for downloads half-way through this example.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.250 docker pull postgres
   ...
   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.251 docker pull postgres
   ...
   alice@mercury:~/flocker-postgres$


Launch PostgreSQL
=================

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


Connect to PostgreSQL
=====================

We can now use the ``psql`` client on our host machine (you will need to install this if you do not already have it) to connect to the PostgreSQL server running inside the container.
Connect using the client to the IP address of our virtual machine, using the port number we exposed in our application config.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ psql postgres --host 172.16.255.250 --port 5432 --username postgres
   psql (9.3.5)
   Type "help" for help.

   postgres=#


Insert a Row in the Database
============================

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

Our last command ``\quit`` quits the client.


Create a New Deployment Config and Move the Application
=======================================================

Download the new deployment configuration and save to your ``flocker-postgres`` directory.

:download:`postgres-deployment-moved.yml`

.. literalinclude:: postgres-deployment-moved.yml
   :language: yaml

Now run ``flocker-deploy`` on the new config:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ flocker-deploy postgres-deployment-moved.yml postgres-application.yml
   alice@mercury:~/flocker-postgres$

Now we'll verify that our application has moved to the other VM:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.251 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   51b5b09a46bb        clusterhq/postgres:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   postgres-volume-example
   alice@mercury:~/flocker-postgres$

And is no longer running on the original host:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   alice@mercury:~/flocker-postgres$

Verify Our Data Has Moved with the Application
==============================================

Query the `flockertest` database for the data we previously inserted.
You will find `flocker` has moved our volume with the container and our data has been preserved.

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

This concludes our example for using `flocker` with PostgreSQL.
Now you've successfully followed through both our tutorial and a further working example of what you can do with flocker, you may now wish to read through the :doc:`../advanced/index`.
