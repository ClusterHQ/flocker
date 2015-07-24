.. _authenticate:

==============
Authentication
==============

The Flocker REST API uses TLS to secure and authenticate requests.
This ensures an API request is both encrypted, and verified to have come from an authorized user, while the corresponding response is verified to have come from the genuine cluster control service.

Certificates are used for both client and server authentication, entirely replacing the use of usernames and passwords commonly used in HTTPS.

Therefore to grant a user access to your cluster's REST API, you will need to use the ``flocker-ca`` tool, installed as part of the ``flocker-cli`` package, to generate a certificate and private key that is then given to the API end user.
To give a user access to a cluster's REST API, use the ``flocker-ca`` tool to generate a certificate and private key for the user.
The ``flocker-ca`` tool is installed as part of the flocker-cli package.
If you have not already followed these steps, see the :ref:`flocker-node installation instructions <installing-flocker>`.

.. _generate-api:

Generating an API user certificate
==================================

The CLI package includes the ``flocker-ca`` program which is used to generate certificate and key files.

.. note:: You can run ``flocker-ca --help`` for a full list of available commands.

For API user certificates, run the ``flocker-ca create-api-certificate`` command from the directory which contains the certificate authority files generated when you first :ref:`installed the cluster <authentication>`.

Run ``flocker-ca create-api-certificate <username>`` where ``<username>`` is a unique username for an API user:

.. code-block:: console

   $ flocker-ca create-api-certificate allison
   Created allison.crt and allison.key. You can now give these to your API end user so they can access the control service API.

.. note:: In this command ``<username>`` is a unique username for an API user.
   Please note though that ``flocker-deploy`` requires these files to be named :file:`user.crt` and :file:`user.key`.
   If you intend on using ``flocker-deploy``, you will need to rename your files to :file:`user.crt` and :file:`user.key`.

The two files generated will correspond to the username you specified in the command, in this example :file:`allison.crt` and :file:`allison.key`.

You should securely provide a copy of these files to the API end user, as well as a copy of the cluster's public certificate, the :file:`cluster.crt` file.

Using an API certificate to authenticate
========================================

Once in possession of an API user certificate and the cluster certificate an end user must authenticate with those certificates in every request to the cluster REST API.
The cluster certificate ensures the user is connecting to the genuine API of their cluster.
The client certificate allows the API server to ensure the request is from a genuine, authorized user.
An example of performing this authentication with ``cURL`` is given below.
In this example, ``172.16.255.250`` represents the IP address of the control service.
The following is an example of an authenticated request to create a new container on a cluster.

OS X
^^^^

Make sure you know the common name of the client certificate you will use.
If you just generated the certificate following the :ref:`instructions above <generate-api>`, the common name is ``user-<username>`` where ``<username>`` is whatever argument you passed to ``flocker-ca generate-api-certificate``.
If you're not sure what the username is, you can find the common name like this:

.. code-block:: console

    $ openssl x509 -in user.crt -noout -subject
    subject= /OU=164b81dd-7e5d-4570-99c7-8baf1ffb49d3/CN=user-allison

In this example, ``user-allison`` is the common name.
Import the client certificate into the ``Keychain`` and then refer to it by its common name:

.. code-block:: console

    $ openssl pkcs12 -export -in user.crt -inkey user.key -out user.p12
	Enter Export Password:
	Verifying - Enter Export Password:
    $ security import user.p12 -k ~/Library/Keychains/login.keychain
    $ curl --cacert $PWD/cluster.crt --cert "<common name>" \
         https://172.16.255.250:4523/v1/configuration/containers

Linux
^^^^^

.. code-block:: console

    $ curl --cacert $PWD/cluster.crt --cert $PWD/user.crt --key $PWD/user.key \
         https://172.16.255.250:4523/v1/configuration/containers

You can read more about how Flocker's authentication layer works in the :ref:`security and authentication guide <security>`.

Next Steps
==========

The next section describes how to :ref:`control Flocker using the CLI<cli>`.
However, now you have set up an authenticated user you may want to perform the steps in :ref:`the MongoDB tutorial <movingapps>` to ensure that your nodes are correctly configured.
You can replace the IP addresses in the sample :file:`deployment.yml` files with the IP addresses of your own nodes, but keep in mind that the tutorial was designed with local virtual machines in mind, and results in an insecure environment.
