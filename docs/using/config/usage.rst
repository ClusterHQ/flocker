============================
Arguments and Authentication
============================

Flocker manages which containers are running and on what hosts.
It also manages network configuration for these containers (between them and between containers and the world).
And Flocker also creates and replicates volumes.
All of this functionality is available via a simple invocation of the ``flocker-deploy`` program.
This program is included in the ``flocker-cli`` package.
If you haven't :ref:`installed that package <installflocker>` yet, you may want to do so now.

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

For ``flocker-deploy``, your API user certificate and key should be in files named ``user.crt`` and ``user.key`` and the cluster certificate in file ``cluster.crt``.

By default, ``flocker-deploy`` will look for these certificate files in the current working directory.
If this is not where the files are located, you may specify the ``--certificates-directory`` option to ``flocker-deploy``:

.. code-block:: console

   $ flocker-deploy --certificates-directory=/home/alice/flocker-credentials 172.16.255.250 clusterhq_deployment.yml clusterhq_app.yml

