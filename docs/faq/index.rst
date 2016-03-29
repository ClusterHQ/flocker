.. _faqs:

====
FAQs
====

.. contents::
   :local:
   :backlinks: none
   :depth: 2

Troubleshooting
---------------

Flocker doesn’t seem to working, how can I check the logs?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you think the Flocker services are running correctly you can check the services or logs in a few different ways.
For checking the dataset agent service and logs you can use the below.
The commands are the same for the other services as well.

On Ubuntu:

.. prompt:: bash $

   service flocker-dataset-agent status
   tail /var/log/flocker/flocker-dataset-agent

On CentOS / RHEL:

.. prompt:: bash $

   systemctl status flocker-dataset-agent -l
   journalctl -a -u flocker-dataset-agent

Using Docker containers:

.. prompt:: bash $

   docker logs <name or UID of Flocker container>

My volume says it’s in a different state than I expected, why is this?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are a number of reasons this could happen.
Your volume could be in detached, pending, attached, or deleted state.
If you volume is in a different state than expected, then the backend and see what is happening with your volume, or you may check the Flocker logs for any indication of issues or errors.

If you continue to have errors, please contact support@clusterhq.com where we may be able to help.

What happens when the node where my container is running dies, crashes or restarts?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Flocker will make sure the volume is detached, re-attached and mounted to the correct node when the container starts on a new healthy node, you will not have to manage these operations manually.

What happens when the node where my container is running freezes or locks up?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If the node your container is running on freezes or locks up then Flocker may not be able to instruct the volume to move or the container using the volume may not be able to stop because no process may be able to tell it to stop.

If you instructure allows it, you can restart or terminate your node and Flocker will be able to operate on the volume.
If it does not, you may need wait to see if the node returns to being healthy.

Why does the ``uft-flocker-volumes`` command not work?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This prefix ``uft`` was removed in favor of ``flockerctl``

Using Flocker
-------------

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

Can I run Flocker with local storage?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Flocker integrates with many storage platforms including software defined storage platforms like EMC ScaleIO, Hedvig, Ceph, and ConvergIO.

Flocker is not a platform that manages local storage such as existing HDD or SSD disks on your server, so you should choose a backend that is suitable for your needs.

Can I contribute a new Flocker storage backend?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Yes, for more information see :ref:`contribute-flocker-driver`.

There are additional FAQs specifically relating to contributing a new Flocker storage backend.
These can be found :ref:`here <build-flocker-driver-faq>`.

Can more than one container access the same volume?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Flocker works by creating a 1:1 relationship of a volume and a container.
This means you can have multiple volumes for one container and those volumes will always follow that container.
Flocker attached volumes to the individual agent host (docker host) and this can only be one host at a time because Flocker attaches Block-based storage.
Nodes on different hosts cannot access the same volume because it can only be attached to one node at a time.
If multiple containers on the same host want to use the same volume, they can, but be careful because multiple containers accessing the same block storage volume can cause corruption.
In order for Flocker to support multiple attachments it would need to support a network filesystem like NFS, GlusterFS or multi-attach based storage.

Can Flocker work across availability zones in AWS or regions in Cinder?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Not currently, this is because volumes are only allowed to attach to nodes in their zone or region.
We will eventually work on support to allow your volumes to move from one zone or region to another.

Can Flocker work with multiple :file:`agent.yml` configurations?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Not currently, a single Flocker cluster can only be configured with one storage backend at a time.

What other storage backends does it work with?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Please view our supported storage backends here: :ref:`storage-backends`

Is there performance benchmarks vs NFS?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

No, we are attacking mainly block storage use cases where volumes are attached via iSCSI or Fiber Channel.
You can use NFS and block storage side by side, they are not exclusive.

Can I attach a single volume to multiple hosts?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Not currently,  support from multi-attach backends like GCE in Read Only mode or NFS-like backends like storage or distributed filesystems like glusterfs would need to be integrated.
Flocker focuses mainly on block-storage uses cases that attach a volume to a single node at a time.

Does Flocker Control support HA?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

No, the control service is not HA and has no integration with key values storage, though it is on our future roadmap. The control service can stop and all containers and dataset will continue to function. If you want to provide sudo-HA for the control service you can. The control service saves a json file in /var/lib/flocker/ which you can take periodic backups of and in case of failure you can easily restore the control service as long as you replace the json file and have all the needed certificates that were used by the failed control service. Backing up your control and cluster certificates along with the json file is a good idea.

Are AWS IAM roles supports with AWS?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Not currently, our AWS backend just uses ACCESS KEY/ ACCESS TOKEN

Are volume snapshots supported with Flocker?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Not yet.

What happened to ZFS support?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

ZFS actually moves data bits around your data center when you need volumes to move, because of this it was inherently slower for the use-cases Flocker is tackling. Flocker can do everything and more than it did with ZFS with its other backends. ZFS also has a number of inefficiencies that lead us to move away from support for ZFS and focus on the other backends that we currently support. We are excited that ZFS was adopted by Canonical/Ubuntu as well as that we understand some people liked ZFS but at this moment it is not supported. That being said, if we see or hear reasons to support it again, we are always open to having the conversations of why you think we should, so feel free to reach out.

Will you support Nomad, RancherOS, etc?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If we find that enough users want support for Flocker in other frameworks or project then we will certainly consider it. We have looked at adding support to Rancher in the past but it’s been shelved currently.

Will you support Rkt?
^^^^^^^^^^^^^^^^^^^^^

Yes. Likely, If the Open Container Initiative does its part in ensuring a stable api across container we see no reason why we can’t let users plugin and play with other container models.

Security
--------

I think I've found a security problem, what should I do?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you think you've found a security problem with Flocker (or any other ClusterHQ software), please send a message to security@clusterhq.com.
Your message will be forwarded to the ClusterHQ security team (a small group of trusted developers) for triage and it will not be publicly readable.

Due to the sensitive nature of security issues, we ask you not to send a message to one of the public mailing lists.
ClusterHQ has a policy for :ref:`reporting-security-issues` designed to minimize any damage that could be inflicted through public knowledge of a defect while it is still outstanding.

Does Flocker handle security policies?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

At the moment Flocker is configured to use SSL/TLS for its agent and control service communication.
However, most security policies that have to do with containers are left to the container runtime or orchestration framework.
Likewise security for volume is managed via the backend that is chosen to run with Flocker.
Flocker doesn’t provide any other container-to-volume based security.

I’m getting in openssl error when I start flocker services, what should I do?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Make sure when your create your certificates that you use a DNS or IP name for the control service certificate.
This will make communicating with the control service from your agent nodes easier in the long run.

If you create your control service certificate with the name ``my-control-service``, then your :file:`agent.yml` must also reference the control service as ``my-control-service``.
This means that you must make that name DNS resolvable in order to avoid ssl issues.
If you use a DNS name or IP, then the configuration is more natural.

For more information on authentication, see :ref:`authentication-standalone-flocker`.
   
If you have further issues with SSL, please contact support@clusterhq.com.

Can I use OpenSSL certificates instead of the flocker-ca tool?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It’s not officially supported yet, but there is a repository that you can use for experimental support for openssl. OpenSSL with Flocker


About ClusterHQ
---------------

What is the working relationship with the Docker team?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We communicate often, such as drivers for the development of the docker plugins was a large collaboration driven by ClusterHQ and other early pioneers in the industry.

What is the working relationship with the Mesos team?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We have active members in the community that enable Flocker integrations with Mesos

What is the working relationship with Storage Vendors?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Third party storage backend drivers are written by the vendors themselves often times we assist with this task.

If you have issues with any of our backend drivers please notify us and we will work closely with our partners to resolve it in a timely fashion.

