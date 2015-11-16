.. _generate-api:

==================================
Generating an API User Certificate
==================================

If you wish to send instructions to the control service, by using the API directly, via the CLI, or any other method, you will need to follow the instructions below to generate an API user certificate:

#. Generate an API user certificate:

   Run the following command from the directory which contains the certificate authority files generated when you first installed the cluster. For more information, see :ref:`authentication`.

   Replace ``<username>`` with a unique username for an API user.

   .. prompt:: bash $

      flocker-ca create-api-certificate <username>

   You will now have the files :file:`<username>.crt` and :file:`<username>.key`.

#. Provide the certificates to the API end user:

   You can now copy the following files to the API end user via a secure communication medium, such as SSH, SCP or SFTP:
   
   * :file:`<username>.crt`
   * :file:`<username>.key`
   * :file:`cluster.crt`

   .. note:: In this example ``<username>`` is a unique username for an API user.
			 Please note though that ``flocker-deploy`` requires these files to be renamed :file:`user.crt` and :file:`user.key`.

Using an API Certificate to Authenticate
========================================

Once in possession of an API user certificate and the cluster certificate, an API end user must authenticate with those certificates in every request to the cluster REST API.
The cluster certificate ensures the user is connecting to the genuine API of their cluster.
The client certificate allows the API server to ensure the request is from a genuine, authorized user.

The following is an example of an authenticated request to create a new container on a cluster, using ``cURL``.
In this example, ``172.16.255.250`` represents the DNS IP address of the control service.
If you used a DNS name when creating the control certificate, then replace the IP address with the DNS name.

.. contents::
   :local:
   :backlinks: none
   :depth: 1

OS X
----

Make sure you know the common name of the client certificate you will use.
If you just generated the certificate following the :ref:`instructions above <generate-api>`, the common name is ``user-<username>`` where ``<username>`` is whatever argument you passed to ``flocker-ca generate-api-certificate``.
If you're not sure what the username is, you can find the common name like this:

.. prompt:: bash $ auto

    $ openssl x509 -in user.crt -noout -subject
    subject=/OU=164b81dd-7e5d-4570-99c7-8baf1ffb49d3/CN=user-allison

In this example, ``user-allison`` is the common name.
Import the client certificate into the ``Keychain`` and then refer to it by its common name:

.. prompt:: bash $ auto

    $ openssl pkcs12 -export -in user.crt -inkey user.key -out user.p12
	Enter Export Password:
	Verifying - Enter Export Password:
    $ security import user.p12 -k ~/Library/Keychains/login.keychain
    $ curl --cacert $PWD/cluster.crt --cert "<common name>" \
         https://172.16.255.250:4523/v1/configuration/containers

Linux
-----

.. prompt:: bash $

    curl --cacert $PWD/cluster.crt --cert $PWD/user.crt --key $PWD/user.key \
         https://172.16.255.250:4523/v1/configuration/containers

You can read more about how Flocker's authentication layer works in the :ref:`security and authentication guide <security>`.
