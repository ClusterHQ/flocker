Flocker Tutorial
================

Examples
========

.. include:: minimal-application.yml
.. include:: minimal-deployment.yml

Before you can deploy this application you'll need a node onto which to deploy it.
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

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ ssh-add ~/.vagrant.d/insecure_private_key

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps

.. code-block:: shell

   alice@mercury:~/flocker-tutorial$ flocker-deploy minimal-deployment.yml minimal-application.yml
   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
