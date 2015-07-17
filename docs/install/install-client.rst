.. _installing-flocker-cli:

=============================
Installing the Flocker Client
=============================

The Flocker CLI is installed on your local machine and provides command line tools to control the cluster. 
This also includes the ``flocker-ca`` tool, which you use to generate certificates for all the Flocker components.

The Flocker agents are installed on any number of nodes in the cluster where your containers will run.
The agent software is included in the ``clusterhq-flocker-node`` package.

There is also a Flocker control service which you must install on one of the agent hosts, or on a separate machine. 
The control service is also included in the ``clusterhq-flocker-node`` package, but is activated separately later in these installation instructions.

.. note:: The agents and control service are pre-installed by the :ref:`Vagrant configuration in the tutorial <tutvagrant>`.

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :ref:`contribute`.

This document will describe how to install the CLI locally and install the agents and control service on cloud infrastructure.
It also describes how to get Vagrant nodes started which already have these services running.

The following sections describe how to install the Flocker client on your platform:

.. contents::
   :local:
   :backlinks: none
   :depth: 2

.. _installing-flocker-cli-ubuntu-15.04:

Ubuntu 15.04
============

On Ubuntu 15.04, the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: install_cli ubuntu-15.04
   :prompt: alice@mercury:~$

.. _installing-flocker-cli-ubuntu-14.04:

Ubuntu 14.04
============

On Ubuntu 14.04, the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: install_cli ubuntu-14.04
   :prompt: alice@mercury:~$

Other Linux Distributions
=========================

.. warning::

   These are guidelines for installing Flocker on a Linux distribution which we do not provide native packages for.
   These guidelines may require some tweaks, depending on the details of the Linux distribution in use.

Before you install ``flocker-cli`` you will need a compiler, Python 2.7, and the ``virtualenv`` Python utility installed.

To install these with the ``yum`` package manager, run:

.. prompt:: bash alice@mercury:~$

   sudo yum install gcc python python-devel python-virtualenv libffi-devel openssl-devel

To install these with ``apt``, run:

.. prompt:: bash alice@mercury:~$

   sudo apt-get update
   sudo apt-get install gcc libssl-dev libffi-dev python2.7 python-virtualenv python2.7-dev

Then run the following script to install ``flocker-cli``:

:version-download:`linux-install.sh.template`

.. version-literalinclude:: linux-install.sh.template
   :language: sh

Save the script to a file and then run it:

.. prompt:: bash alice@mercury:~$

   sh linux-install.sh

The ``flocker-deploy`` command line program will now be available in :file:`flocker-tutorial/bin/`:

.. version-code-block:: console

   alice@mercury:~$ cd flocker-tutorial
   alice@mercury:~/flocker-tutorial$ bin/flocker-deploy --version
   |latest-installable|
   alice@mercury:~/flocker-tutorial$

If you want to omit the prefix path you can add the appropriate directory to your ``$PATH``.
You'll need to do this every time you start a new shell.

.. version-code-block:: console

   alice@mercury:~/flocker-tutorial$ export PATH="${PATH:+${PATH}:}${PWD}/bin"
   alice@mercury:~/flocker-tutorial$ flocker-deploy --version
   |latest-installable|
   alice@mercury:~/flocker-tutorial$

OS X
====

Install the `Homebrew`_ package manager.

Make sure Homebrew has no issues:

.. prompt:: bash alice@mercury:~$

   brew doctor

Fix anything which ``brew doctor`` recommends that you fix by following the instructions it outputs.

Add the ``ClusterHQ/tap`` tap to Homebrew and install ``flocker``:

.. task:: test_homebrew flocker-|latest-installable|
   :prompt: alice@mercury:~$

You can see the Homebrew recipe in the `homebrew-tap`_ repository.

The ``flocker-deploy`` command line program will now be available:

.. version-code-block:: console

   alice@mercury:~$ flocker-deploy --version
   |latest-installable|
   alice@mercury:~$

Next Step
=========

The next section describes your next step - :ref:`Installing the Flocker Node Services<installing-flocker-node>`.

.. _Homebrew: http://brew.sh
.. _homebrew-tap: https://github.com/ClusterHQ/homebrew-tap
