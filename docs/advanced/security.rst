=================================
Cluster Security & Authentication
=================================

A Flocker cluster comprises a control service and convergence agents, along with some command line tools that are provided to interact with, and manage the cluster. For more information, see :doc:`architecture`.

Flocker uses `Transport Layer Security <http://en.wikipedia.org/wiki/Transport_Layer_Security>`_ (TLS) to authenticate components of a cluster, in a `mutual authentication  <http://en.wikipedia.org/wiki/Mutual_authentication>`_ model.

This ensures that the control service, convergence agents, and API end users are communicating with a verified component of a cluster, helping to prevent unauthorised access, and mitigating some potential attack vectors.

Client Certification Overview
=============================

When :doc:`installing the flocker-node package <../indepth/installation>`, the ``flocker-ca`` tool (provided as part of ``flocker-cli``) generates a certificate authority for your cluster, as well as certificates and private keys for the control service and convergence agents.

A certification authority certificate, also known as a root certificate, is a type of TLS certificate that is used to generate other certificates, by signing another key's `certificate signing request <http://en.wikipedia.org/wiki/Certificate_signing_request>`_ with its own private key.
The certificate authority is an individual or organisation that is trusted to generate certificates signed with its own private key.
In the context of Flocker, the certificate authority is the cluster administrator.

This mutual authentication process, where certificates signed by a private key known only to the cluster administrator, are used to establish connections and to provide a means to verify the identity of an entity, such as the control service or an API end user, which presents itself as being an authorised component of a cluster.

For example, if a convergence agent receives a request to change the state of a cluster node from a machine identifying itself as that cluster's control service, it can check that the TLS data received was encrypted using the key of a certificate signed by the cluster's known certificate authority.
Further, some data can be sent encrypted to the control service using the public key of the signed certificate presented by the control service.
If the control service is able to send the same data back encrypted with the public key presented by the convergence agent's signed certificate, both sides of the communication are verified that the other holds the private key corresponding to their respective certificates.

Provided that the cluster administrator has kept the private key of the certificate authority secure (that is, the key file has not been shared or copied anywhere), this identification process confirms that the machine the node is talking to is indeed the genuine control service for the cluster and vice-versa.
All components of a Flocker cluster identify themselves to each other in this way.
By providing this identity verification layer, the cluster is able to prevent unauthorised attempts to interact with the control service, convergence agents, and REST API.

Security Benefits
=================

The TLS client certification layer used by Flocker provides a number of security benefits to a cluster:

- Prevents unauthorised requests to the REST API.
- Prevents `man-in-the-middle <http://en.wikipedia.org/wiki/Man-in-the-middle_attack>`_ and `identity replay <http://en.wikipedia.org/wiki/Replay_attack>`_ attacks between the control service and convergence agents by verifying the identity of cluster components.
- Encrypts communications over the public internet between the control service and convergence agents.
- Encrypts communications between the control service and an API end user.
- Prevents connections to the control service and convergence agents from unidentified or unauthorised sources.
- Prevents communications between API users, the control service, and convergence agents from being altered or tampered with in transit over the public internet.
- Verifies the identity of cluster components and API users.

Risks
=====

Flocker's authentication layer does not completely guarantee the security of a cluster; it relies on the private keys of the cluster's certificate authority, control service, convergence agents, and API users being kept secret.

For example, if a malicious user were able to gain root SSH access to the machine running the control service, they would be able to copy the control service's private key and therefore be able to set up another machine to act and identify as the legitimate control service for that cluster.

Similarly, if the private key of an API end user is compromised, anyone with that key will be able to authenticate as that authorised user, and therefore make requests to the REST API to read or change the state of a cluster.

It is therefore very important that you ensure the private keys are kept secure; they should not be copied or shared insecurely.
When copying certificates and private keys to your cluster nodes as part of the ``flocker-node`` installation process, the files must be copied using a secure and encrypted transfer medium such as SSH, SCP or SFTP.

Other measures that would normally be taken to secure a server should still be implemented; Flocker is not a full server stack and its security layer does not prevent your server being hacked, rather it mitigates the likelihood of Flocker services being used as a vector to do so.
