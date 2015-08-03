.. _security:

=================================
Cluster Security & Authentication
=================================

A Flocker cluster comprises a control service and convergence agents, along with some command line tools that are provided to interact with, and manage the cluster. For more information, see :ref:`architecture`.

Flocker uses `Transport Layer Security <https://en.wikipedia.org/wiki/Transport_Layer_Security>`_ (TLS) to authenticate components of a cluster, in a `mutual authentication <https://en.wikipedia.org/wiki/Mutual_authentication>`_ model.

This ensures that the control service, convergence agents, and API end users are communicating with a verified component of a cluster, helping to prevent unauthorized access, and mitigating some potential attack vectors.

Mutual Authentication Overview
==============================

When :ref:`installing the flocker-node package <installing-flocker>`, the ``flocker-ca`` tool (provided as part of ``flocker-cli``) generates a root certificate for your cluster, comprising a private key and public certificate, as well as certificates and private keys for the control service and convergence agents.
The certificates and private keys for the control service and nodes are installed on the cluster alongside the cluster's root public certificate file.

API end users are issued their own certificate and private key, also with a copy of the cluster's public certificate file.

This allows all components of the cluster to establish both a private channel of communication and a means of verifying identity; the client validates the server certificate was signed by the cluster authority, while the server mutually verifies the client's certificate was signed by the same authority.

Security Benefits
=================

The TLS client certification layer used by Flocker provides a number of security benefits to a cluster.

- Prevents unauthorized requests to the REST API.
- Prevents unauthorized connections to the control service and convergence agents.
- Encrypts communications between all components of the cluster.

Risks
=====

Flocker's authentication layer does not completely guarantee the security of a cluster; it relies on the private keys of the cluster's certificate authority, control service, convergence agents, and API users being kept secret.

For example, if a malicious user were able to gain root SSH access to the machine running the control service, they would be able to copy the control service's private key and therefore be able to set up another machine to act and identify as the legitimate control service for that cluster.

Similarly, if the private key of an API end user is compromised, anyone with that key will be able to authenticate as that authorized user, and therefore make requests to the REST API to read or change the state of a cluster.

It is therefore very important that you ensure the private keys are kept secure; they should not be copied or shared insecurely.
When copying certificates and private keys to your cluster nodes as part of the ``flocker-node`` installation process, the files must be copied using a secure and encrypted transfer medium such as SSH, SCP or SFTP.

Other measures that would normally be taken to secure a server should still be implemented; Flocker is not a full server stack and its security layer does not prevent your server being hacked, rather it mitigates the likelihood of Flocker services being used as a vector to do so.
