Flocker Tutorial
================

TODO: tease the data functionality up front before going through the long
boring process of introducing all the non-data features

Setup
~~~~~

Before you can deploy anything with Flocker you'll need a node onto which to deploy it.
To make this easier, this tutorial includes and assumes the use of a Vagrant configuration which will provide you with VMs that can serve as Flocker nodes.
For this basic example, use this ``Vagrantfile`` to create one VM:

.. include:: Vagrantfile

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ vagrant up node1
   Bringing machine 'node1' up with 'virtualbox' provider...
   ==> node1: Importing base box 'clusterhq/flocker-dev'...
   ... lots of output ...
   ==> node1: ln -s '/usr/lib/systemd/system/docker.service' '/etc/systemd/system/multi-user.target.wants/docker.service'
   ==> node1: ln -s '/usr/lib/systemd/system/geard.service' '/etc/systemd/system/multi-user.target.wants/geard.service'
   alice@mercury:~/flocker-tutorial$

This step may take several minutes or more.
Beyond just booting a virtual machine to use as a node for the tutorial, it will download and build the necessary ZFS kernel modules.
Your network connectivity and CPU speed will affect how long this takes.
Fortunately this extra work is only necessary the first time you bring up a node (until you destroy it).

After the ``vagrant`` command completes you may want to verify that the VM is really running and accepting SSH connections:

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ vagrant status node1
   Current machine states:

   node1                     running (virtualbox)
   ...
   alice@mercury:~/flocker-tutorial$ vagrant ssh node1
   Last login: Wed Jul 16 07:51:58 2014 from 10.0.2.2
   Welcome to your Packer-built virtual machine.
   [vagrant@node1 ~]$

If all goes well, the next step is to configure your SSH agent.
This will allow Flocker to authenticate itself to the VM.
Make sure you have an SSH agent running:

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ kill -0 ${SSH_AGENT_PID} && echo "yes"
   yes
   alice@mercury:~/flocker-tutorial$

If you aren't then start one now:

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ eval $(ssh-agent)
   Agent pid 27233
   alice@mercury:~/flocker-tutorial$

Then add the Vagrant key to your agent:

   alice@mercury:~/flocker-tutorial$ ssh-add ~/.vagrant.d/insecure_private_key
   alice@mercury:~/flocker-tutorial$

This completes the Vagrant-related setup.

Starting an Application
~~~~~~~~~~~~~~~~~~~~~~~

Let's look at an extremely simple Flocker configuration for one node running a container containing a MongoDB database.

.. include:: minimal-application.yml
.. include:: minimal-deployment.yml

Next take a look at what containers Docker is running on the VM you just created:

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE    COMMAND    CREATED    STATUS     PORTS     NAMES
   alice@mercury:~/flocker-tutorial$

From this you can see that there are no running containers.
To fix this, use ``flocker-deploy`` with the simple configuration files given above and then check again:

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ flocker-deploy minimal-deployment.yml minimal-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    dockerfile/mongodb:latest   mongod     2 seconds ago   Up 1 seconds   27017/tcp, 28017/tcp   mongodb-example
   alice@mercury:~/flocker-tutorial$

``flocker-deploy`` has made the necessary changes to make your node match the state described in the configuration files you supplied.

Let's see how ``flocker-deploy`` can move this application to a different VM.
Start a second node so you have someplace to move it to:

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ vagrant up node2
   Bringing machine 'node2' up with 'virtualbox' provider...
   ...
   ==> node2: ln -s '/usr/lib/systemd/system/docker.service' '/etc/systemd/system/multi-user.target.wants/docker.service'
   ==> node2: ln -s '/usr/lib/systemd/system/geard.service' '/etc/systemd/system/multi-user.target.wants/geard.service'
   alice@mercury:~/flocker-tutorial$

Now edit the *deployment* configuration file so that it indicates the application should run on this new node:

.. include:: minimal-deployment-moved.yml

Note that nothing in the application configuration file needs to change.
*Moving* the application only involves updating the deployment configuration.

Now use ``flocker-deploy`` again to enact the change and take a look at what containers are running where:

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ flocker-deploy minimal-deployment-moved.yml minimal-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID    IMAGE    COMMAND    CREATED    STATUS     PORTS     NAMES
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.251 docker ps
   CONTAINER ID    IMAGE                       COMMAND    CREATED         STATUS         PORTS                  NAMES
   4d117c7e653e    dockerfile/mongodb:latest   mongod     3 seconds ago   Up 2 seconds   27017/tcp, 28017/tcp   mongodb-example
   alice@mercury:~/flocker-tutorial$

At this point you have successfully deployed a MongoDB server in a container on your VM.
You've also seen how Flocker provides basic orchestration functionality
There's no way to interact with it apart from looking at the ``docker ps`` output yet, though.
The next step is to expose it in the host's network interface.

Exposing an Application
~~~~~~~~~~~~~~~~~~~~~~~

A

