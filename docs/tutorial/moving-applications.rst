===================
Moving Applications
===================

Starting an Application
=======================

Let's look at an extremely simple Flocker configuration for one node running a container containing a MongoDB server.

:download:`minimal-application.yml`

.. literalinclude:: minimal-application.yml
   :language: yaml

:download:`minimal-deployment.yml`

.. literalinclude:: minimal-deployment.yml
   :language: yaml

Next take a look at what containers Docker is running on the VM you just created.
The node IPs are those which were specified earlier in the ``Vagrantfile``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE    COMMAND    CREATED    STATUS     PORTS     NAMES
   alice@mercury:~/flocker-tutorial$

From this you can see that there are no running containers.
To fix this, use ``flocker-deploy`` with the simple configuration files given above and then check again:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy minimal-deployment.yml minimal-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    dockerfile/mongodb:latest   mongod     2 seconds ago   Up 1 seconds   27017/tcp, 28017/tcp   mongodb-example
   alice@mercury:~/flocker-tutorial$

``flocker-deploy`` has made the necessary changes to make your node match the state described in the configuration files you supplied.


Moving an Application
=====================

Let's see how ``flocker-deploy`` can move this application to a different VM.
Start a second node so you have somewhere to move it to:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ vagrant up node2
   Bringing machine 'node2' up with 'virtualbox' provider...
   ...
   ==> node2: ln -s '/usr/lib/systemd/system/docker.service' '/etc/systemd/system/multi-user.target.wants/docker.service'
   ==> node2: ln -s '/usr/lib/systemd/system/geard.service' '/etc/systemd/system/multi-user.target.wants/geard.service'
   alice@mercury:~/flocker-tutorial$

Now edit the *deployment* configuration file so that it indicates the application should run on this new node.
The only change necessary to indicate this is to change the original IP address, ``172.16.255.250``, to the address of the other node, ``172.16.255.251``.

.. literalinclude:: minimal-deployment-moved.yml
   :language: yaml
   :emphasize-lines: 3

Note that nothing in the application configuration file needs to change.
*Moving* the application only involves updating the deployment configuration.

Use ``flocker-deploy`` again to enact the change:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy minimal-deployment-moved.yml minimal-application.yml
   alice@mercury:~/flocker-tutorial$

``docker-ps`` can show that no applications are running on ``172.16.255.250``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE    COMMAND    CREATED    STATUS     PORTS     NAMES
   alice@mercury:~/flocker-tutorial$

and that MongoDB has been successfully moved to ``172.16.255.251``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.251 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    dockerfile/mongodb:latest   mongod     3 seconds ago   Up 2 seconds   27017/tcp, 28017/tcp   mongodb-example
   alice@mercury:~/flocker-tutorial$

At this point you have successfully deployed a MongoDB server in a container on your VM.
You've also seen how Flocker provides basic orchestration functionality
There's no way to interact with it apart from looking at the ``docker ps`` output yet, though.
The next step is to expose it in the host's network interface.
