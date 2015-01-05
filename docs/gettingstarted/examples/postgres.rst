:tocdepth: 1

==================
Running PostgreSQL
==================

.. This section is tested in flocker.acceptance.test_postgres.PostgresTests.
   Reflect any relevant changes here in those tests.

Create the Virtual Machines
===========================

You can reuse the Virtual Machines defined in the Vagrant configuration for :doc:`the MongoDB tutorial <../tutorial/index>`.
If you have since shutdown or destroyed those VMs, boot them up again:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ vagrant up
   Bringing machine 'node1' up with 'virtualbox' provider...
   ==> node1: Importing base box 'clusterhq/flocker-dev'...

Launch PostgreSQL
=================

Download and save the following configuration files to your ``flocker-tutorial`` directory:

:download:`postgres-application.yml`

.. literalinclude:: postgres-application.yml
   :language: yaml

:download:`postgres-deployment.yml`

.. literalinclude:: postgres-deployment.yml
   :language: yaml

Now run ``flocker-deploy`` to deploy the PostgreSQL application to the target Virtual Machine.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy postgres-deployment.yml postgres-application.yml
   alice@mercury:~/flocker-tutorial$

Confirm the container is running in its destination host:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   f6ee0fbd0446        postgres:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   postgres-volume-example
   alice@mercury:~/flocker-tutorial$


Connect to PostgreSQL
=====================

You can now use the ``psql`` client on the host machine to connect to the PostgreSQL server running inside the container.
Connect using the client to the IP address of the Virtual Machine, using the port number exposed in the application configuration:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ psql postgres --host 172.16.255.250 --port 5432 --username postgres
   psql (9.3.5)
   Type "help" for help.

   postgres=#

This verifies the PostgreSQL service is successfully running inside its container.

Insert a Row into the Database
==============================

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

Download and save the following configuration file to your ``flocker-tutorial`` directory:

:download:`postgres-deployment-moved.yml`

.. literalinclude:: postgres-deployment-moved.yml
   :language: yaml

Then run ``flocker-deploy`` to move the PostgreSQL application along with its data to the new destination host:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy postgres-deployment-moved.yml postgres-application.yml
   alice@mercury:~/flocker-tutorial$

Verify Data Has Moved
=====================

Confirm the application has moved to the target Virtual Machine:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.251 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   51b5b09a46bb        clusterhq/postgres:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   postgres-volume-example
   alice@mercury:~/flocker-tutorial$

And is no longer running on the original host:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   alice@mercury:~/flocker-tutorial$

You can now connect to PostgreSQL on its host and confirm the sample data has also moved:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ psql postgres --host 172.16.255.251 --port 5432 --username postgres
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

This concludes the PostgreSQL example.
