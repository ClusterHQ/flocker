===========================
Example: Linking Containers
===========================

Once you've successfully followed through :doc:`./tutorial/index` this example will show you how to deploy an ElasticSearch-Logstash-Kibana stack of linked containers with Flocker.
We'll insert some data, then use ``flocker-deploy`` to move one of the containers to another virtual machine.
The data will be moved along with the application.

The requirements are the same as the MongoDB tutorial.


Create the Virtual Machines
===========================

We'll be using the same Vagrant configuration as :doc:`the MongoDB tutorial <./tutorial/index>`.
If you haven't already started up the Vagrant virtual machines follow the :doc:`setup instructions <./tutorial/vagrant-setup>`.


Download the Docker Images
==========================

(We use the ``-t`` option to ``ssh`` so that progress is displayed; if you omit it the pull will still work but you may not get any output for a long time.)

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh -t root@172.16.255.250 docker pull XXX
   ...
   alice@mercury:~/flocker-elk$ ssh -t root@172.16.255.251 docker pull XXX
   ...
   alice@mercury:~/flocker-elk$


Launch XXX
==========

Download and save the following configuration files to your ``flocker-postgres`` directory:

:download:`elk-application.yml`

.. literalinclude:: elk-application.yml
   :language: yaml

:download:`elk-deployment.yml`

.. literalinclude:: elk-deployment.yml
   :language: yaml

Run ``flocker-deploy`` to download the images and get the container running:

.. code-block:: console

   alice@mercury:~/flocker-elk$ flocker-deploy elk-deployment.yml elk-application.yml
   alice@mercury:~/flocker-elk$

You can keep running ``ssh root@172.16.255.250 docker ps`` until you see the container running:

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   f6ee0fbd0446        XXX:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   XXX-XXX-XXX
   alice@mercury:~/flocker-elk$

Connect to XXX
==============

Connect to the IP address of our virtual machine, using the port number we exposed in our application configuration.

.. code-block:: console

   alice@mercury:~/flocker-elk$ XXX
   > XXX
   > exit
   alice@mercury:~/flocker-elk$


Add some data
=============

XXX


Create a New Deployment Configuration and Move the Application
==============================================================

Download the new deployment configuration and save to your ``flocker-elk`` directory.

:download:`elk-deployment-moved.yml`

.. literalinclude:: elk-deployment-moved.yml
   :language: yaml

Now run ``flocker-deploy`` on the new configuration:

.. code-block:: console

   alice@mercury:~/flocker-elk$ flocker-deploy elk-deployment-moved.yml elk-application.yml
   alice@mercury:~/flocker-elk$

Now we'll verify that our application has moved to the other VM:

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh root@172.16.255.251 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   51b5b09a46bb        clusterhq/XXX:latest   /bin/sh -c /init    7 seconds ago       Up 6 seconds        0.0.0.0:5432->5432/tcp   XXX
   alice@mercury:~/flocker-postgres$

And is no longer running on the original host:

.. code-block:: console

   alice@mercury:~/flocker-elk$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                       COMMAND             CREATED             STATUS              PORTS                    NAMES
   alice@mercury:~/flocker-elk$

Verify Our Data Has Moved with the Application
==============================================

Query the ``flockertest`` database for the data we previously inserted.
You will find that Flocker has moved our volume with the container and our data has been preserved.

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

This concludes our example for using Flocker with PostgreSQL.
Now you've successfully followed through both our tutorial and a further working example of what you can do with flocker, you may now wish to read through the :doc:`../advanced/index`.

.. _`PostgreSQL`: https://www.postgresql.org/download/
