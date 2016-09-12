.. Single Source Instructions

=============================
Installing the Flocker Client
=============================

.. begin-body-installing-client-intro

The following sections describe how to install the Flocker client on your platform:

.. contents::
   :local:
   :backlinks: none
   :depth: 2

.. end-body-installing-client-intro

.. _installing-flocker-cli-ubuntu-16.04:

.. begin-body-installing-client-Ubuntu-16.04

Installing on Ubuntu 16.04 (64-bit)
===================================

.. note::
   These instructions require that you have ``sudo`` access.

   If you are using a 32-bit Ubuntu platform, see the instructions for Installing on Other Linux Distributions.

On Ubuntu 16.04 (64-bit), the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: cli_pkg_install ubuntu-16.04
   :prompt: alice@mercury:~$

.. end-body-installing-client-Ubuntu-16.04

.. _installing-flocker-cli-ubuntu-14.04:

.. begin-body-installing-client-Ubuntu-14.04

Installing on Ubuntu 14.04 (64-bit)
===================================

.. note::
   These instructions require that you have ``sudo`` access.

   If you are using a 32-bit Ubuntu platform, see the instructions for Installing on Other Linux Distributions.

On Ubuntu 14.04 (64-bit), the Flocker CLI can be installed from the ClusterHQ repository:

.. task:: cli_pkg_install ubuntu-14.04
   :prompt: alice@mercury:~$

.. end-body-installing-client-Ubuntu-14.04

.. _installing-flocker-cli-rhel-7.2:

.. begin-body-installing-client-rhel-7.2

Installing on RHEL 7.2
======================

.. note::
   These instructions require that you have ``sudo`` access.


On RHEL 7.2, the Flocker CLI can be installed from the ClusterHQ repository:

.. prompt:: bash root@rhel:~$

   yum install -y clusterhq-flocker-cli

.. end-body-installing-client-rhel-7.2

.. _installing-flocker-cli-linux:

.. begin-body-installing-client-linux


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
   alice@mercury:~$ flocker-ca --version
   |latest-installable|

.. end-body-installing-client-linux

.. begin-body-installing-client-OSX

Installing on OS X
==================

Install ``pip`` and ``virtualenv`` on your machine at the system level:

.. prompt:: bash alice@mercury:~$

   sudo python -m ensurepip
   sudo pip install virtualenv

To install ``flocker-cli`` in a Python virtualenv, run:

.. task:: cli_pip_install flocker-client
   :prompt: alice@mercury:~$

If you are prompted to install command line developer tools at any point,
please install the tools and then re-run whatever command failed in the
background.

Whenever you need to run Flocker CLI commands, ensure you are in the virtualenv:

.. version-prompt:: bash alice@mercury:~$ auto

   alice@mercury:~$ source flocker-client/bin/activate
   alice@mercury:~$ flocker-ca --version
   |latest-installable|

.. end-body-installing-client-OSX
