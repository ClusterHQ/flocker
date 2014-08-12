==================
Installing Flocker
==================

As a user of Flocker you will need to install the ``flocker-cli`` package which provides command line tools to control the cluster.
This should be installed on a machine with SSH credentials to control the cluster nodes
(e.g., if you use our Vagrant setup then the machine which is running Vagrant).

There is also a ``flocker-node`` package which is installed on each node in the cluster.
It contains the ``flocker-changestate``, ``flocker-reportstate``, and ``flocker-volume`` utilities. 
These utilities are called by ``flocker-deploy`` (via SSH) to install and migrate Docker containers and their data volumes.

.. note:: For now, the ``flocker-node`` package is pre-installed by the `Vagrant configuration in the tutorial <tutorial>`_. 
          In the next release it will be distributed as a standalone package which you will be able to install on an existing Fedora 20 server.

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :doc:`../gettinginvolved/contributing`.

.. _installing-flocker-cli:

Installing flocker-cli
======================

Linux
-----

Before you install ``flocker-cli`` you will need a compiler, Python 2.7 and the ``virtualenv`` Python utility installed.
On Fedora 20 you can do so by running:

.. code-block:: console

   alice@mercury:~$ sudo yum install @buildsys-build python python-devel python-virtualenv

On Ubuntu or Debian you can run:

.. code-block:: console

   alice@mercury:~$ sudo apt-get install gcc python2.7 python-virtualenv python2.7-dev

Then run the following script to do the actual install:

:download:`linux-install.sh`

.. literalinclude:: linux-install.sh
   :language: sh

Save the script to a file and then run it:

.. code-block:: console

   alice@mercury:~$ sh linux-install.sh
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

Fix anything which ``brew doctor`` recommends that you fix by following the instructions it outputs.

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

.. _`Homebrew`: http://brew.sh
