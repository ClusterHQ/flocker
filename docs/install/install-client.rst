.. _installing-flocker-cli:

.. note::

    Want to get started with Flocker quickly?

    Try the :ref:`Installer <labs-installer>`.
    It makes it easy to set up and manage a Flocker cluster.
    It runs inside a Docker container on your local machine.

    If you use the Installer then you don't need to follow the instructions on this page.

=============================
Installing the Flocker Client
=============================

The following sections describe how to install the Flocker client on your platform:

.. contents::
   :local:
   :backlinks: none
   :depth: 2

.. _installing-flocker-cli-ubuntu-15.04:

Ubuntu 15.04
============

.. note:: These instructions require that you have ``sudo`` access.

On Ubuntu 15.04, the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: cli_pkg_install ubuntu-15.04
   :prompt: alice@mercury:~$

.. _installing-flocker-cli-ubuntu-14.04:

Ubuntu 14.04
============

.. note:: These instructions require that you have ``sudo`` access.

On Ubuntu 14.04, the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: cli_pkg_install ubuntu-14.04
   :prompt: alice@mercury:~$

Other Linux Distributions
=========================

.. warning::

   These are guidelines for installing Flocker on a Linux distribution for which we do not provide native packages.
   These guidelines may require some tweaks, depending on the details of the Linux distribution in use.

.. note:: These instructions require that you have ``sudo`` access.

Before you install ``flocker-cli`` you will need a compiler, Python 2.7, and the ``virtualenv`` Python utility installed.

To install these pre-requisites with the ``yum`` package manager, run:

.. task:: cli_pip_prereqs yum
   :prompt: alice@mercury:~$


To install these pre-requisites with the ``apt`` package manager, run:

.. task:: cli_pip_prereqs apt
   :prompt: alice@mercury:~$

To install ``flocker-cli`` in a Python virtualenv, run:

.. task:: cli_pip_install flocker-client
   :prompt: alice@mercury:~$

Whenever you need to run Flocker CLI commands, ensure you are in the virtualenv:

.. task:: cli_pip_test flocker-client
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

.. version-prompt:: bash alice@mercury:~$ auto

   alice@mercury:~$ flocker-deploy --version
   |latest-installable|

Next Step
=========

The next section describes your next step - :ref:`Installing the Flocker Node Services<installing-flocker-node>`.

.. _Homebrew: http://brew.sh
.. _homebrew-tap: https://github.com/ClusterHQ/homebrew-tap
