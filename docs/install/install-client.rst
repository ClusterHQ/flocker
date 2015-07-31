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

   These are guidelines for installing Flocker on a Linux distribution for which we do not provide native packages.
   These guidelines may require some tweaks, depending on the details of the Linux distribution in use.

Before you install ``flocker-cli`` you will need a compiler, Python 2.7, and the ``virtualenv`` Python utility installed.

To install these pre-requisites with the ``yum`` package manager, run:

.. task:: cli_pip_prereqs centos-7
   :prompt: alice@mercury:~$


To install these pre-requisites with the ``apt`` package manager, run:

.. task:: cli_pip_prereqs ubuntu-15.04
   :prompt: alice@mercury:~$

Then run the following commands to install ``flocker-cli`` in a Python virtualenv:

.. task:: cli_pip_install
   :prompt: alice@mercury:~$

Ensure you are in the virtualenv whenever you need to run Flocker CLI commands:

.. task:: cli_pip_test
   :prompt: alice@mercury:~$

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
