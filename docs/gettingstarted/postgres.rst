===========================
Example: Running PostgreSQL
===========================

Once you've successfully followed through :doc:`./tutorial/index` this example will show you how to deploy a lightweight PostgreSQL container with Flocker.
We've pre-prepared a micro PostgreSQL container image which is publicly available on the Docker registry.
In this example, we'll download the image and use ``flocker-deploy`` to deploy the app to a container in a virtual machine.
We'll insert some data, then use ``flocker-deploy`` to move the PostgreSQL server container to another virtual machine.
Our data will be carried over along with the application.

Create the virtual machines
===========================

We'll be using the same Vagrant configuration as :doc:`./tutorial/index`:

* :download:`Vagrant configuration <./tutorial/Vagrantfile>`
* :download:`Flocker repository configuration <./tutorial/clusterhq-flocker.repo>`

Create a new directory on your local machine, for example *flocker-postgres* and save these files to that location.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ls
   clusterhq-flocker.repo  Vagrantfile
   alice@mercury:~/flocker-postgres$

Next use ``vagrant up`` to start and provision the VMs:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ vagrant up
   Bringing machine 'node1' up with 'virtualbox' provider...
   ==> node1: Importing base box 'clusterhq/flocker-dev'...
   ... lots of output ...
   ==> node2: ln -s '/usr/lib/systemd/system/docker.service' '/etc/systemd/system/multi-user.target.wants/docker.service'
   ==> node2: ln -s '/usr/lib/systemd/system/geard.service' '/etc/systemd/system/multi-user.target.wants/geard.service'
   alice@mercury:~/flocker-postgres$

As with the tutorial, this step may take several minutes to complete.

Launching the PostgreSQL server
===============================

Download and save the following configuration files to your ``flocker-postgres`` directory:

:download:`postgres-application.yml`

.. literalinclude:: postgres-application.yml
   :language: yaml

:download:`postgres-deployment.yml`

.. literalinclude:: postgres-deployment.yml
   :language: yaml

As you can see, we will be pulling the ``clusterhq/postgres`` image and deploying to one of our virtual nodes.
Run ``flocker-deploy`` to download the image and get the container running:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ flocker-deploy postgres-deployment.yml postgres-application.yml
   alice@mercury:~/flocker-postgres$

**Note:** It may take a few extra seconds after ``flocker-deploy`` completes for the container to launch inside the VM.
You can keep running ``ssh root@172.16.255.250 docker ps`` until you see the container running:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   f6ee0fbd0446        clusterhq/postgres:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   postgres-volume-example

Get the PostgreSQL password
===========================

Our pre-built Docker image for PostgreSQL includes a randomly generated password.
We can retrieve this by inspecting the logs for our container, using the container ID we obtained above.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.250 docker logs f6ee0fbd0446
   PG_PASSWORD=365ff19669
   LOG:  database system was shut down at 2014-08-11 11:00:17 UTC
   LOG:  database system is ready to accept connections
   LOG:  autovacuum launcher started
   alice@mercury:~/flocker-postgres$

Connect to the PostgreSQL server
================================

We can now use the ``psql`` client on our host machine (you will need to install this if you do not already have it) to connect to the PostgreSQL server running inside the container.
Connect using the client to the IP address of our virtual machine, using the port number we exposed in our application config.
You will need to enter the password we obtained above when prompted by the client.

.. code-block:: console

   alice@mercury:~/flocker-postgres$ psql postgres --host 172.16.255.250 --port 5432 --username postgres
   Password for user postgres: 
   psql (9.3.5, server 9.2.4)
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

Verify our data has moved with the application
==============================================

Finally, we'll connect via the `psql` client once more to verify that our data has been successfully moved alongside the application.

Our example PostgreSQL image generates a new random password for the `postgres` user each time it's run, so we'll need to grab the new password via `docker logs`.
Grab the container ID running on `172.16.255.251` form the output of the `docker ps` command above and run it in to `docker logs`:

.. code-block:: console

   alice@mercury:~/flocker-postgres$ ssh root@172.16.255.251 docker logs 51b5b09a46bb
   PG_PASSWORD=9c1eb9e47b
   LOG:  database system was shut down at 2014-08-11 11:00:17 UTC
   LOG:  database system is ready to accept connections
   LOG:  autovacuum launcher started
   alice@mercury:~/flocker-postgres$

.. code-block:: console

   alice@mercury:~/flocker-postgres$ psql postgres --host 172.16.255.251 --port 5432 --username postgres
   Password for user postgres: 
   psql (9.3.5, server 9.2.4)
   Type "help" for help.
   
   postgres=# \l
                                  List of databases
        Name    |  Owner   | Encoding  | Collate | Ctype |   Access privileges   
   -----------+----------+-----------+---------+-------+-----------------------
    postgres    | postgres | SQL_ASCII | C       | C     | 
    template0   | postgres | SQL_ASCII | C       | C     | =c/postgres          +
                |          |           |         |       | postgres=CTc/postgres
    template1   | postgres | SQL_ASCII | C       | C     | =c/postgres          +
                |          |           |         |       | postgres=CTc/postgres
    flockertest | postgres | SQL_ASCII | C       | C     | =c/postgres          +
                |          |           |         |       | postgres=CTc/postgres
   (4 rows)

Query the `flockertest` database for the data we previously inserted.
You will find `flocker` has moved our volume with the container and our data has been preserved.

.. code-block:: console
   
   postgres=# \c flockertest;
   psql (9.3.5, server 9.2.4)
   You are now connected to database "flockertest" as user "postgres".
   flockertest=# select * from testtable;
    testcolumn 
   ------------
             3
   (1 row)
   
   flockertest=# \q


---------------------------------

This concludes our example for using `flocker` with PostgreSQL.
Now you've successfully followed through both our tutorial and a further working example of what you can do with flocker, you may now wish to read through the :doc:`../advanced/index`.
