==============
Authentication
==============

The Flocker REST API uses TLS certification to authenticate both client API requests and communication between the control service and nodes on a cluster.
To set up this authentication layer, you will need to generate certificates for each component of your cluster. The program to do this is included as part of the ``flocker-cli`` package, so you will need to :doc:`install that package <../../indepth/installation>` to get started.

Overview
========

1. You generate a self-signed certificate authority with the ``flocker-ca`` program.
   This writes out a certificate file and a private key file.
2. The self-signed authority identifies components within your cluster and will be used to sign the certificates generated for the control service, node agents and API clients.
   These certificates and keys are also generated using ``flocker-ca``.
3. You copy the control service and node agent certificates on to your cluster nodes and supply the API client certificates to the API endusers.
   This allows the endusers to perform :doc:`API requests <./api>` that will be actioned by the cluster control service.


The flocker-ca Tool
===================

The CLI package includes the ``flocker-ca`` program which is used to generate certificate and key files.

.. code-block:: console

    $ flocker-ca --help

    Usage: flocker-ca <command> [OPTIONS]
    Options:
          --version  Print the program's version and exit.
          --help     Display this help and exit.
      -v, --verbose  Turn on verbose logging.

    flocker-ca is used to create TLS certificates.      The certificates are used to
    identify the control service, nodes and     API clients within a Flocker
    cluster.
    Commands:
        initialize                      Initialize a certificate authority in the current
                                        working directory.
        create-control-certificate      Create a certificate for the control service.

Generating a Certificate Authority
----------------------------------

Run ``flocker-ca initialize <name>`` where ``<name>`` is a unique identifier for your cluster.
This will create the certificate file ``cluster.crt`` and key file ``cluster.key`` in the current working directory.

.. code-block:: console

    $ flocker-ca initialize mycluster
    Created cluster.key and cluster.crt. Please keep cluster.key secret, as anyone who can access it will be able to control your cluster.

Generating a Control Service Certificate
----------------------------------------

In the directory containing your authority certificate and key files, run ``flocker-ca create-control-certificate``.
This will generate the files ``control-service.crt`` and ``control-service.key`` in the current working directory.

.. code-block:: console

   $ flocker-ca create-control-certificate
   Created control-service.crt. Copy it over to /etc/flocker/control-service.crt on your control service machine and make sure to chmod 0600 it.
