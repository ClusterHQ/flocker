.. _tutorial-requirements:

================
Before You Begin
================

.. _tutorial-prerequisites:

Prerequisites
=============

For this tutorial, you will need:

* Linux, FreeBSD, or OS X
* Two virtual machines with at least 10 GB disk space available.
  Follow the steps in :ref:`vagrant-setup` to set up virtual machines using `Vagrant`_ and `VirtualBox`_
* The OpenSSH client (the ``ssh``, ``ssh-agent``, and ``ssh-add`` command line programs)
* bash
* The ``flocker-cli`` installed.
  For more information, see :ref:`installing-cli`.
* The ``mongo`` MongoDB interactive shell.
  For more information, see :ref:`installing-mongoDB`.

.. _installing-cli:

Installing the Flocker CLI
==========================

You will need to have the ``flocker-cli`` installed, which provides the ``flocker-deploy`` command.
For more information, see :ref:`installing-flocker-cli`.

If you have a version of ``flocker-cli`` installed that is older than |version|, follow the instructions in :ref:`installing-flocker-cli` to install the latest version.

.. _installing-mongoDB:

Installing MongoDB
==================

The MongoDB client can be installed through the various package managers for Linux, FreeBSD, and OS X.
If you do not already have the client on your machine, you can install it by running the appropriate command for your system.

Ubuntu
------

.. prompt:: bash alice@mercury:~$

   sudo apt-get install mongodb-clients

Red Hat / Fedora
----------------

.. prompt:: bash alice@mercury:~$

   sudo yum install mongodb

OS X
----

Install `Homebrew`_

.. prompt:: bash alice@mercury:~$

   brew update
   brew install mongodb

Other Systems
-------------

See the official `MongoDB installation guide`_ for your system.

.. _`Homebrew`: http://brew.sh/
.. _`Vagrant`: https://docs.vagrantup.com/v2/
.. _`VirtualBox`: https://www.virtualbox.org/
.. _`MongoDB installation guide`: https://docs.mongodb.org/manual/installation/
