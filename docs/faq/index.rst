.. _faqs:

====
FAQs
====

Flocker
-------

Can I run Flocker with local storage?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Flocker integrates with many storage platforms including software defined storage platforms like EMC ScaleIO, Hedvig, Ceph, and ConvergIO.

Flocker is not a platform that manages local storage such as existing HDD or SSD disks on your server, so you should choose a backend that is suitable for your needs.

Can more than one container access the same volume?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Flocker works by creating a 1:1 relationship of a volume and a container.
This means you can have multiple volumes for one container and those volumes will always follow that container.
Flocker attached volumes to the individual agent host (docker host) and this can only be one host at a time because Flocker attaches Block-based storage.
Nodes on different hosts cannot access the same volume because it can only be attached to one node at a time.
If multiple containers on the same host want to use the same volume, they can, but be careful because multiple containers accessing the same block storage volume can cause corruption.
In order for Flocker to support multiple attachments it would need to support a network filesystem like NFS, GlusterFS or multi-attach based storage.

How do I integrate Flocker with Docker Swarm?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Flocker Swarm is Docker native!
This means you can use our Docker volume driver to easily integrate with Swarm.

Here are some useful links for more information:

* :ref:`Using Flocker with Docker, Swarm, Compose <docker-integration>`
* :ref:`about-docker-integration`


How do I integrate Flocker with Kubernetes?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Here are some useful links for more information:

* :ref:`Using Flocker with Kubernetes <kubernetes-integration>`
* `Demo: High Availability with Kubernetes and Flocker <https://clusterhq.com/2015/12/22/ha-demo-kubernetes-flocker/>`_
* `Tutorial: Deploying a Replicated Redis Cluster on Kubernetes with Flocker <https://clusterhq.com/2016/02/11/kubernetes-redis-cluster/>`_

How do I integrate Flocker with Mesos?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are two ways to integrate Flocker with Mesos.
The first is via the Flocker Framework, and the other is through the use of our Docker volume driver and the Docker containerizer.  Learn more in the following links.



Security
--------

I think I've found a security problem, what should I do?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you think you've found a security problem with Flocker (or any other ClusterHQ software), please send a message to security@clusterhq.com.
Your message will be forwarded to the ClusterHQ security team (a small group of trusted developers) for triage and it will not be publicly readable.

Due to the sensitive nature of security issues, we ask you not to send a message to one of the public mailing lists.
ClusterHQ has a policy for :ref:`reporting-security-issues` designed to minimize any damage that could be inflicted through public knowledge of a defect while it is still outstanding.

I’m getting in openssl error when I start flocker services, what should I do?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Make sure when your create your certificates that you use a DNS or IP name for the control service certificate.
This will make communicating with the control service from your agent nodes easier in the long run.

If you create your control service certificate with the name ``my-control-service``, then your :file:`agent.yml` must also reference the control service as ``my-control-service``.
This means that you must make that name DNS resolvable in order to avoid ssl issues.
If you use a DNS name or IP, then the configuration is more natural.

For more information on authentication, see :ref:`authentication-standalone-flocker`.
   
If you have further issues with SSL, please contact support@clusterhq.com.

There are additional FAQs specifically relating to contributing a new Flocker storage backend.
These can be found :ref:`here <build-flocker-driver-faq>`.
