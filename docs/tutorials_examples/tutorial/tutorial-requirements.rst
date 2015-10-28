.. _tutorial-requirements:

================
Before You Begin
================

.. note::
	To start this tutorial, you will need to have installed the ``flocker-cli``, which provides the ``flocker-deploy`` command.
	For more information, see :ref:`installing-flocker-cli`.

	If you have a version of ``flocker-cli`` installed that is older than |version|, delete the install script and directory, and install the latest version.

Requirements
============

To replicate the steps demonstrated in this tutorial, you will need:

* Linux, FreeBSD, or OS X
* `Vagrant`_ (1.6.2 or newer)
* `VirtualBox`_
* At least 10GB disk space available for the two virtual machines
* The OpenSSH client (the ``ssh``, ``ssh-agent``, and ``ssh-add`` command line programs)
* bash
* The ``mongo`` MongoDB interactive shell (see below for installation instructions)

Setup
=====

Installing MongoDB
------------------

The MongoDB client can be installed through the various package managers for Linux, FreeBSD and OS X.
If you do not already have the client on your machine, you can install it by running the appropriate command for your system.

Ubuntu
^^^^^^

.. prompt:: bash alice@mercury:~$

   sudo apt-get install mongodb-clients

Red Hat / Fedora
^^^^^^^^^^^^^^^^

.. prompt:: bash alice@mercury:~$

   sudo yum install mongodb

OS X
^^^^

Install `Homebrew`_

.. prompt:: bash alice@mercury:~$

   brew update
   brew install mongodb

Other Systems
^^^^^^^^^^^^^

See the official `MongoDB installation guide`_ for your system.

.. _`Homebrew`: http://brew.sh/
.. _`Vagrant`: https://docs.vagrantup.com/v2/
.. _`VirtualBox`: https://www.virtualbox.org/
.. _`MongoDB installation guide`: http://docs.mongodb.org/manual/installation/
