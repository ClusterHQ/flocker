.. _authentication:

==================================
Configuring Cluster Authentication
==================================

.. note:: 
	The following steps describe how to configure authentication for your cluster.
	These can only be completed once you have installed the Flocker client and node services, as described in the previous :ref:`Installing Flocker <installing-flocker>` section.

Communication between the different parts of your cluster is secured and authenticated via TLS.
The Flocker CLI package includes the ``flocker-ca`` tool that is used to generate TLS certificate and key files that you will need to copy over to your nodes.

#. Once you have installed the ``flocker-node`` package, you will need to generate:

   - A control service certificate and key file, to be copied over to the machine running your :ref:`control service <architecture>`.
   - A certificate and key file for each of your nodes, which you will also need to copy over to the nodes.

#. Both types of certificate will be signed by a certificate authority identifying your cluster, which is also generated using the ``flocker-ca`` tool.

#. Using the machine on which you installed the ``flocker-cli`` package, run the following command to generate your cluster's root certificate authority, replacing ``mycluster`` with any name you like to uniquely identify this cluster.

   .. prompt:: bash 

      flocker-ca initialize mycluster

   .. note:: This command creates :file:`cluster.key` and :file:`cluster.crt`.
             Please keep :file:`cluster.key` secret, as anyone who can access it will be able to control your cluster.

   You will find the files :file:`cluster.key` and :file:`cluster.crt` have been created in your working directory.

#. The file :file:`cluster.key` should be kept only by the cluster administrator; it does not need to be copied anywhere.

   .. warning:: The cluster administrator needs this file to generate new control service, node and API certificates.
                The security of your cluster depends on this file remaining private.
                Do not lose the cluster private key file, or allow a copy to be obtained by any person other than the authorized cluster administrator.

#. You are now able to generate authentication certificates for the control service and each of your nodes.
   To generate the control service certificate, run the following command from the same directory containing your authority certificate generated in the previous step:

   - Replace ``example.org`` with the hostname of your control service node; this hostname should match the hostname you will give to HTTP API clients.
   - It should be a valid DNS name that HTTPS clients can resolve since they will use it as part of TLS validation.
   - Using an IP address is not recommended as it may break some HTTPS clients.

     .. code-block:: console

        $ flocker-ca create-control-certificate example.org

#. At this point you will need to create a :file:`/etc/flocker` directory on each node:

   .. code-block:: console

      root@centos-7:~/$ mkdir /etc/flocker

#. You will need to copy both :file:`control-example.org.crt` and :file:`control-example.org.key` over to the node that is running your control service, to the directory :file:`/etc/flocker` and rename the files to :file:`control-service.crt` and :file:`control-service.key` respectively.
   You should also copy the cluster's public certificate, the :file:`cluster.crt` file.

#. On the server, the :file:`/etc/flocker` directory and private key file should be set to secure permissions via :command:`chmod`:

   .. code-block:: console

      root@centos-7:~/$ chmod 0700 /etc/flocker
      root@centos-7:~/$ chmod 0600 /etc/flocker/control-service.key

   You should copy these files via a secure communication medium such as SSH, SCP or SFTP.

   .. warning:: Only copy the file :file:`cluster.crt` to the control service and node machines, not the :file:`cluster.key` file; this must kept only by the cluster administrator.

#. You will also need to generate authentication certificates for each of your nodes.
   Do this by running the following command as many times as you have nodes; for example, if you have two nodes in your cluster, you will need to run this command twice.

   This step should be followed for all nodes on the cluster, as well as the machine running the control service.
   Run the command in the same directory containing the certificate authority files you generated in the first step.

   .. code-block:: console

      $ flocker-ca create-node-certificate

   This creates :file:`8eab4b8d-c0a2-4ce2-80aa-0709277a9a7a.crt`. Copy it over to :file:`/etc/flocker/node.crt` on your node machine, and make sure to chmod 0600 it.

   The actual certificate and key file names generated in this step will vary from the example above; when you run ``flocker-ca create-node-certificate``, a UUID for a node will be generated to uniquely identify it on the cluster and the files produced are named with that UUID.

#. As with the control service certificate, you should securely copy the generated certificate and key file over to your node, along with the :file:`cluster.crt` certificate.

   - Copy the generated files to :file:`/etc/flocker` on the target node and name them :file:`node.crt` and :file:`node.key`.
   - Perform the same :command:`chmod 600` commands on :file:`node.key` as you did for the control service in the instructions above.
   - The :file:`/etc/flocker` directory should be set to ``chmod 700``.

You should now have :file:`cluster.crt`, :file:`node.crt`, and :file:`node.key` on each of your agent nodes, and :file:`cluster.crt`, :file:`control-service.crt`, and :file:`control-service.key` on your control node.

Before you can use Flocker's API you will need to generate a client certificate.

The Flocker REST API also uses TLS to secure and authenticate requests.
This ensures an API request is both encrypted, and verified to have come from an authorized user, while the corresponding response is verified to have come from the genuine cluster control service.

Certificates are used for both client and server authentication, entirely replacing the use of usernames and passwords commonly used in HTTPS.

Therefore to grant a user access to your cluster's REST API, you will need to use the ``flocker-ca`` tool, installed as part of the ``flocker-cli`` package, to generate a certificate and private key that is then given to the API end user.
To give a user access to a cluster's REST API, use the ``flocker-ca`` tool to generate a certificate and private key for the user.
The ``flocker-ca`` tool is installed as part of the flocker-cli package.

.. _generate-api:

Generating an API User Certificate
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

Using an API Certificate to Authenticate
========================================

Once in possession of an API user certificate and the cluster certificate an end user must authenticate with those certificates in every request to the cluster REST API.
The cluster certificate ensures the user is connecting to the genuine API of their cluster.
The client certificate allows the API server to ensure the request is from a genuine, authorized user.
An example of performing this authentication with ``cURL`` is given below.
In this example, ``172.16.255.250`` represents the IP address of the control service.
The following is an example of an authenticated request to create a new container on a cluster.

OS X
----

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
-----

.. code-block:: console

    $ curl --cacert $PWD/cluster.crt --cert $PWD/user.crt --key $PWD/user.key \
         https://172.16.255.250:4523/v1/configuration/containers

You can read more about how Flocker's authentication layer works in the :ref:`security and authentication guide <security>`.
