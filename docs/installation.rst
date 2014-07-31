==================
Installing Flocker
==================

As a user of Flocker there are two components you will need to install:

1. The ``flocker-node`` package that runs on each node in the cluster.
   This package is installed on machines which will run Docker containers.
2. The ``flocker-cli`` package which provides command line tools to controls the cluster.
   This should be installed on a machine with SSH credentials to control the cluster nodes
   (e.g., if you use our Vagrant setup then the machine which is running Vagrant).

Installing flocker-node
=======================
If you're interested in developing Flocker (as opposed to simply using it) see :doc:`contributing`.

For now we strongly recommend running the cluster using our pre-packaged Vagrant setup;
see :doc:`tutorial/vagrant-setup` for details.

If you would like to install ``flocker-node`` on a Fedora 20 host you are managing some other way, you can do so:

  1. Configure ``yum`` with the Flocker package repository and install the Flocker node package:

     .. code-block:: sh

        yum localinstall http://archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm
        yum localinstall http://archive.clusterhq.com/fedora/flocker-release$(rpm -E %dist).noarch.rpm
        yum install flocker-node

  2. Create a ZFS pool.
     For testing purposes, you can create a pool on a loopback device on your existing filesystem:

     .. code-block:: sh

        mkdir -p /opt/flocker
        truncate --size 1G /opt/flocker/pool-vdev
        zpool create flocker /opt/flocker/pool-vdev

Installing flocker-cli
======================

Fedora 20
---------

To install ``flocker-cli`` on Fedora 20 you can install the RPM provided by the ClusterHQ repository:

.. code-block:: sh

   yum localinstall http://archive.clusterhq.com/fedora/flocker-release$(rpm -E %dist).noarch.rpm
   yum install flocker-cli

Verify the client is installed:

.. code-block:: console

   alice@mercury:~$ flocker-deploy --version
   0.1.0


Debian / Ubuntu
---------------

To install ``flocker-cli`` on Debian or Ubuntu you can run the following script:

:download:`ubuntu-install.sh`

.. literalinclude:: ubuntu-install.sh
   :language: sh

Save the script to a file and then run it:

.. code-block:: console

   alice@mercury:~$ sh ubuntu-install.sh

The ``flocker-deploy`` command line program will now be available in ``flocker-tutorial/bin/``:

.. code-block:: console

   alice@mercury:~$ cd flocker-tutorial
   alice@mercury:~/flocker-tutorial$ bin/flocker-deploy --version
   0.1.0
   alice@mercury:~/flocker-tutorial$ export PATH="${PATH:+${PATH}:}${PWD}/bin"
   alice@mercury:~/flocker-tutorial$ flocker-deploy --version
   0.1.0

OS X
----

To install ``flocker-cli`` on OS X you can run the following script:

:download:`osx-install.sh`

.. literalinclude:: osx-install.sh
   :language: sh

Save the script to a file and then run it:

.. code-block:: console

   alice@mercury:~$ sh osx-install.sh

The ``flocker-deploy`` command line program will now be available in ``flocker-tutorial/bin/``:

.. code-block:: console

   alice@mercury:~$ cd flocker-tutorial
   alice@mercury:~/flocker-tutorial$ bin/flocker-deploy --version
   0.1.0
   alice@mercury:~/flocker-tutorial$ export PATH="${PATH:+${PATH}:}${PWD}/bin"
   alice@mercury:~/flocker-tutorial$ flocker-deploy --version
   0.1.0
