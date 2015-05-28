.. _cli-testing:

Client Testing
==============

There are automated acceptance tests for the Flocker CLI on some platforms.
See :ref:`client-acceptance-tests`.

Sometimes it is useful to manually test CLIs and their installation instructions on various platforms.

OS X
----

ClusterHQ has a Mac with the ability to start an OS X Virtual Machine.
An internal document describing how to use this is available at "Infrastructure > OS X Development Machine".

Linux
-----

To test on various Linux distributions, it is possible to create either Docker containers or Vagrant virtual machines.

Using Docker
^^^^^^^^^^^^

To create a Docker container, choose a Docker image from the `Docker Hub <https://registry.hub.docker.com>`_, and start it as below:

.. prompt:: bash $

   docker run -i -t ubuntu /bin/bash

or:

.. prompt:: bash $

   docker run -i -t fedora:20 /bin/bash

for example.

This will likely allow you to test commands as a root user.
If you want to test as a non-root user, create a new user which has the ability to use ``sudo``.

Using Vagrant
^^^^^^^^^^^^^

To create a Vagrant virtual machine, choose a Vagrant box from `Atlas <https://atlas.hashicorp.com/boxes/search>`_ and start it as below:

.. prompt:: bash $

   vagrant init ubuntu/trusty64
   vagrant up
   vagrant ssh

for example.
