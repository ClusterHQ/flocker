============================
Arguments and Authentication
============================

Flocker manages which containers are running and on what hosts.
It also manages network configuration for these containers (between them and between containers and the world).
And Flocker also creates and replicates volumes.
All of this functionality is available via a simple invocation of the ``flocker-deploy`` program.
This program is included in the ``flocker-cli`` package.
If you haven't :ref:`installed that package <installing-flocker>` yet, you may want to do so now.

Command Line Arguments
======================

``flocker-deploy`` takes three arguments:

1. The hostname of the machine where the control service (including the Flocker REST API) is running.
2. The path to a deployment configuration file.
3. The path to an application configuration file.

.. code-block:: console

    $ flocker-deploy controlservice.example.com clusterhq_deployment.yml clusterhq_app.yml

The contents of the two configuration files determine what actions Flocker actually takes by replacing the existing cluster configuration.
See :ref:`configuration` for details about the two files.

You can run ``flocker-deploy`` anywhere you have it installed.
The containers you are managing do not need to be running on the same host as ``flocker-deploy``\ .

Authentication
==============

Setup
-----

``flocker-deploy`` lets you manage containers on one or more hosts.

Before ``flocker-deploy`` can do this it needs to be able to authenticate itself to these hosts.

Flocker uses TLS mutual authentication to communicate with the control service you specify as the first command line argument.

To authenticate with the control service, you will need a copy of the public cluster certificate created when you first :ref:`installed flocker on your nodes <authentication>` and an API user certificate, which you can :ref:`generate <generate-api>` using the ``flocker-ca`` tool.

By default, ``flocker-deploy`` will look for these certificate files in the current working directory and expect them to be named :file:`cluster.crt` (the public cluster certificate), :file:`user.crt` (the API user certificate) and :file:`user.key` (the API user's private key).

You can override these defaults with the ``--cacert`` (cluster certificate), ``--cert`` (user certificate) and ``--key`` (user private key) options, specifying the full path to each file.

.. code-block:: console

   $ flocker-deploy --cacert=/home/alice/credentials/mycluster.crt --cert=/home/alice/credentials/alice.crt --key=/home/alice/credentials/alice.key 172.16.255.250 clusterhq_deployment.yml clusterhq_app.yml

