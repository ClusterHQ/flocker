.. _installing-flocker-cli:

=============================
Installing the Flocker Client
=============================

The following sections describe how to install the Flocker client on your platform:

.. contents::
   :local:
   :backlinks: none
   :depth: 2

.. _installing-flocker-cli-ubuntu-15.10:

Installing on Ubuntu 15.10 (64-bit)
===================================

.. note:: 
   These instructions require that you have ``sudo`` access.

   If you are using a 32-bit Ubuntu platform, see the instructions for  :ref:`installing-flocker-cli-linux`.

On Ubuntu 15.10 (64-bit), the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: cli_pkg_install ubuntu-15.10
   :prompt: alice@mercury:~$

.. _installing-flocker-cli-ubuntu-14.04:

Installing on Ubuntu 14.04 (64-bit)
===================================

.. note:: 
   These instructions require that you have ``sudo`` access.

   If you are using a 32-bit Ubuntu platform, see the instructions for  :ref:`installing-flocker-cli-linux`.

On Ubuntu 14.04 (64-bit), the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: cli_pkg_install ubuntu-14.04
   :prompt: alice@mercury:~$

.. _installing-flocker-cli-linux:

Installing on Other Linux Distributions
=======================================

.. warning::

   These are guidelines for installing Flocker on a Linux distribution for which we do not provide native packages.
   These guidelines may require some tweaks, depending on the details of the Linux distribution in use.

.. note:: These instructions require that you have ``sudo`` access.

Before you install ``flocker-cli`` you will need a compiler, Python 2.7, and the ``virtualenv`` Python utility installed.

To install these prerequisites with the ``yum`` package manager, run:

.. task:: cli_pip_prereqs yum
   :prompt: alice@mercury:~$


To install these prerequisites with the ``apt`` package manager, run:

.. task:: cli_pip_prereqs apt
   :prompt: alice@mercury:~$

To install ``flocker-cli`` in a Python virtualenv, run:

.. task:: cli_pip_install flocker-client
   :prompt: alice@mercury:~$

Whenever you need to run Flocker CLI commands, ensure you are in the virtualenv:

.. version-prompt:: bash alice@mercury:~$ auto

   alice@mercury:~$ source flocker-client/bin/activate
   alice@mercury:~$ flocker-deploy --version
   |latest-installable|

Installing on OS X
==================

Install the `Homebrew`_ package manager.

Make sure Homebrew has no issues:

.. prompt:: bash alice@mercury:~$

   brew doctor

Fix anything which ``brew doctor`` recommends that you fix by following the instructions it outputs.

If you have a previous version of Flocker tapped, you can run the following to remove it:

.. prompt:: bash alice@mercury:~$

   brew uninstall flocker-<old version>

Add the ``ClusterHQ/tap`` tap to Homebrew and install ``flocker``:

.. task:: test_homebrew flocker-|latest-installable|
   :prompt: alice@mercury:~$

You can see the Homebrew recipe in the `homebrew-tap`_ repository.

The ``flocker-deploy`` command line program will now be available:

.. version-prompt:: bash alice@mercury:~$ auto

   alice@mercury:~$ flocker-deploy --version
   |latest-installable|

Next Step
=========

The next section describes your next step - :ref:`Installing the Flocker Node Services<installing-flocker-node>`.

.. _Homebrew: http://brew.sh
.. _homebrew-tap: https://github.com/ClusterHQ/homebrew-tap
