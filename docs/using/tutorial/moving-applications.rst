.. _movingapps:

===================
Moving Applications
===================

.. note:: If you haven't already, make sure to :ref:`install the flocker-cli package <installing-flocker-cli>` before continuing with this tutorial.

Starting an Application
=======================

Let's look at an extremely simple Flocker configuration for one node running a container containing a MongoDB server.

:download:`minimal-application.yml`

.. literalinclude:: minimal-application.yml
   :language: yaml

:download:`minimal-deployment.yml`

.. literalinclude:: minimal-deployment.yml
   :language: yaml

Notice that we mention the node that has no applications deployed on it to ensure that ``flocker-deploy`` knows that it exists.
If we hadn't done that certain actions that might need to be taken on that node will not happen, e.g. stopping currently running applications.

Next take a look at what containers Docker is running on the VM you just created.
The node IPs are those which were specified earlier in the ``Vagrantfile``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE    COMMAND    CREATED    STATUS     PORTS     NAMES
   alice@mercury:~/flocker-tutorial$

From this you can see that there are no running containers.
To fix this, use ``flocker-deploy`` with the simple configuration files given above and then check again:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy 172.16.255.250 minimal-deployment.yml minimal-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    clusterhq/mongodb:latest   mongod     2 seconds ago   Up 1 seconds   27017/tcp, 28017/tcp   mongodb-example
   alice@mercury:~/flocker-tutorial$

``flocker-deploy`` has made the necessary changes to make your node match the state described in the configuration files you supplied.


Moving an Application
=====================

.. This section is tested in flocker.acceptance.test_moving_applications.MovingApplicationTests.
   Reflect any relevant changes here in those tests.

Let's see how ``flocker-deploy`` can move this application to a different VM.
Recall that the Vagrant configuration supplied in the setup portion of the tutorial started two VMs.
Copy the *deployment* configuration file and edit it so that it indicates the application should run on the second VM instead of the first.
The only change necessary to indicate this is to change the original IP address, ``172.16.255.250``, to the address of the other node, ``172.16.255.251``.
The new file should be named ``minimal-deployment-moved.yml``.

:download:`minimal-deployment-moved.yml`

.. literalinclude:: minimal-deployment-moved.yml
   :language: yaml
   :emphasize-lines: 3

Note that nothing in the application configuration file needs to change.
*Moving* the application only involves updating the deployment configuration.

Use ``flocker-deploy`` again to enact the change:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy 172.16.255.250 minimal-deployment-moved.yml minimal-application.yml
   alice@mercury:~/flocker-tutorial$

``docker ps`` shows that no containers are running on ``172.16.255.250``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE    COMMAND    CREATED    STATUS     PORTS     NAMES
   alice@mercury:~/flocker-tutorial$

and that MongoDB has been successfully moved to ``172.16.255.251``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.251 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    clusterhq/mongodb:latest   mongod     3 seconds ago   Up 2 seconds   27017/tcp, 28017/tcp   mongodb-example
   alice@mercury:~/flocker-tutorial$

At this point you have successfully deployed a MongoDB server in a container on your VM.
You've also seen how Flocker can move an existing container between hosts.
There's no way to interact with it apart from looking at the ``docker ps`` output yet.
In the next section of the tutorial you'll see how to expose container services on the host's network interface.
