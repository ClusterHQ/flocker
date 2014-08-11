==================
Installing Flocker
==================

As a user of Flocker there are two components you will need to install:

1. The ``flocker-cli`` package which provides command line tools to control the cluster.
   This should be installed on a machine with SSH credentials to control the cluster nodes
   (e.g., if you use our Vagrant setup then the machine which is running Vagrant).

2. The ``flocker-node`` package that runs on each node in the cluster.
   This package is installed on machines which will run Docker containers.

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :doc:`../gettinginvolved/contributing`.

.. _installing-flocker-cli:

Installing flocker-cli
======================

Fedora 20
---------

To install ``flocker-cli`` on Fedora 20 you can install the RPM provided by the ClusterHQ repository:

.. code-block:: sh

   yum localinstall http://archive.clusterhq.com/fedora/clusterhq-release$(rpm -E %dist).noarch.rpm
   yum install flocker-cli

Verify the client is installed:

.. code-block:: console

   alice@mercury:~$ flocker-deploy --version
   0.1.0
   alice@mercury:~$


Debian / Ubuntu
---------------

To install ``flocker-cli`` on Debian or Ubuntu you can run the following script:

:download:`ubuntu-install.sh`

.. literalinclude:: ubuntu-install.sh
   :language: sh

Save the script to a file and then run it:

.. code-block:: console

   alice@mercury:~$ sh ubuntu-install.sh
   ...
   alice@mercury:~$

The ``flocker-deploy`` command line program will now be available in ``flocker-tutorial/bin/``:

.. code-block:: console

   alice@mercury:~$ cd flocker-tutorial
   alice@mercury:~/flocker-tutorial$ bin/flocker-deploy --version
   0.1.0
   alice@mercury:~/flocker-tutorial$

If you want to omit the prefix path you can e.g. add the appropriate directory to your ``$PATH``.
You'll need to do this every time you start a new shell.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ export PATH="${PATH:+${PATH}:}${PWD}/bin"
   alice@mercury:~/flocker-tutorial$ flocker-deploy --version
   0.1.0
   alice@mercury:~/flocker-tutorial$

OS X
----

To install ``flocker-cli`` on OS X you can install ``virtualenv`` and then run the ``flocker-cli`` install script:

Installing virtualenv
^^^^^^^^^^^^^^^^^^^^^

Install the `Homebrew`_ package manager.

Make sure Homebrew has no issues:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ brew doctor
   ...
   alice@mercury:~/flocker-tutorial$

Fix anything which `brew doctor` recommends that you fix by following the instructions it outputs.

Install ``Python``, ``pip`` and ``virtualenv``:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ brew update
   alice@mercury:~/flocker-tutorial$ brew install python
   ...
   alice@mercury:~/flocker-tutorial$ pip install virtualenv
   ...
   alice@mercury:~/flocker-tutorial$


Running the Install Script
^^^^^^^^^^^^^^^^^^^^^^^^^^

:download:`osx-install.sh`

.. literalinclude:: osx-install.sh
   :language: sh

Save the script to a file and then run it:

.. code-block:: console

   alice@mercury:~$ sh osx-install.sh
   ...
   alice@mercury:~$

The ``flocker-deploy`` command line program will now be available in ``flocker-tutorial/bin/``:

.. code-block:: console

   alice@mercury:~$ cd flocker-tutorial
   alice@mercury:~/flocker-tutorial$ bin/flocker-deploy --version
   0.1.0
   alice@mercury:~/flocker-tutorial$

If you want to omit the prefix path you can e.g. add the appropriate directory to your ``$PATH``.
You'll need to do this every time you start a new shell.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ export PATH="${PATH:+${PATH}:}${PWD}/bin"
   alice@mercury:~/flocker-tutorial$ flocker-deploy --version
   0.1.0
   alice@mercury:~/flocker-tutorial$


Installing flocker-node
=======================

.. note:: For now we strongly recommend running the cluster using our custom Fedora 20 virtual machine, which can be built using Vagrant.
          See :doc:`the tutorial setup <tutorial/vagrant-setup>` for details.

To install ``flocker-node`` on an existing Fedora 20 host, follow these steps:

1. Configure ``yum`` with the Flocker package repository and install the Flocker node package:

   .. code-block:: console

      yum localinstall http://archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm
      yum localinstall http://archive.clusterhq.com/fedora/clusterhq-release$(rpm -E %dist).noarch.rpm
      yum install flocker-node

2. Create a ZFS pool.
   For testing purposes, you can create a pool on a loopback device on your existing filesystem:

   .. code-block:: console

      mkdir -p /opt/flocker
      truncate --size 1G /opt/flocker/pool-vdev
      zpool create flocker /opt/flocker/pool-vdev

   .. note:: Refer to the `ZFS on Linux documentation`_ for more information on zpool and other ZFS commands.

.. _`ZFS on Linux documentation`: http://zfsonlinux.org/docs.html
.. _`Homebrew`: http://brew.sh
