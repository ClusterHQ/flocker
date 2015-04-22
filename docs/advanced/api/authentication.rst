==============
Authentication
==============

The Flocker REST API uses TLS certification to secure and authenticate requests.
This ensures an API request is both encrypted and verified to have come from an authorised user, while the corresponding response is verified to have come from the genuine cluster control service.

Unlike regular HTTPS, Flocker uses TLS not just for establishing a secure connection between an API user and the cluster's control service, but also for identity verification; that is, client certification is used in place of a username and password to identify an API user to the cluster.

Therefore to grant a user access to your cluster's REST API, you will need to use the ``flocker-ca`` tool installed as part of the ``flocker-cli`` package to generate a certificate and private key that is then given to the API end user.
When you installed the ``flocker-node`` package on each of your cluster nodes, you should have already used the ``flocker-ca`` tool to generate a root certificate authority identifying your cluster.
If you have not already followed these steps, please see the `flocker-node installation instructions <../indepth/installation>`.

Generate an API user certificate
================================

The CLI package includes the ``flocker-ca`` program which is used to generate certificate and key files.

.. code-block:: console

    $ flocker-ca --help

    Usage: flocker-ca <command> [OPTIONS]
    Options:
          --version  Print the program's version and exit.
          --help     Display this help and exit.
      -v, --verbose  Turn on verbose logging.

    flocker-ca is used to create TLS certificates.
    The certificates are used to identify the control service, nodes
    and API clients within a Flocker cluster.
    Commands:
        initialize                      Initialize a certificate authority in the current
                                        working directory.
        create-control-certificate      Create a certificate for the control service.
        create-node-certificate         Create a certificate for a node.
        create-api-certificate          Create a certificate for an API user.

You will need to run the ``create-api-certificate`` command from the same directory containing the certificate authority files generated when you first installed the cluster.

Run ``flocker-ca create-api-certificate username``, replacing ``username`` with anything you like to uniquely identify an individual API user.

.. code-block:: console

   $ flocker-ca create-api-certificate alice
   Created alice.crt and alice.key. You can now give these to your API enduser so they can access the control service API.

The two files generated will correspond to the username you specified in the command, in this example ``alice.crt`` and ``alice.key``.
You should securely provide a copy these files to the API end user.
Once the user is in possession of these files, for security purposes you should delete the original copies generated.

Using an API certificate to authenticate
========================================

Once in possession of an API user certificate, an end user must authenticate with that certificate in every request to the cluster REST API.
An example of performing this authentication with cURL is given below, where ``172.16.255.250`` represents the IP address of the control service.
The following is an example of an authenticated request to create a new container on a cluster.

.. code-block:: console

   $ curl -H "Content-Type: application/json" -X POST -d '{"host": "172.255.250.251", "name": "webserver", "image": "nginx:latest"}' --cert alice.crt https://172.16.255.250/v1/configuration/containers
   
You can read more about how Flocker's authentication layer works in the :doc:`security and authentication guide <../security>`.
