===========
Cleaning Up
===========

Flocker does not currently implement a tool to purge containers and state from deployment nodes that have had applications and volumes installed via ``flocker-deploy``.
Adding a cleanup tool is `on the Flocker development path`_ for a later release.

Until this feature is available, you may wish to manually purge deployment nodes of all containers and state created by Flocker.
This will enable you to test, play around with Flocker or repeat the deployment process (for example, if you have followed through the tutorial and would like to clean up the virtual machines to start again without having to destroy and rebuild them).

.. note::

   This process will destroy all applications and their associated data deployed by Flocker on the target node.
   In addition, the verbatim commands documented below will destroy **all** Docker containers and ``Geard`` units on the target node, regardless of whether or not they were deployed via Flocker.
   *Proceed at your own risk and only if you fully understand the effects of executing these commands.*

You can run the necessary cleanup commands via SSH. The tutorial's virtual machines are created with IP addresses ``172.16.255.250`` and ``172.16.255.251``.
Be sure to replace the example IP address in the commands below with the actual IP address of the node you wish to purge.


Stopping Containers
===================

Docker containers must be stopped before they can be removed.

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 'docker ps -aq | xargs --no-run-if-empty docker stop'


Removing Containers
===================

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 'docker ps -aq | xargs --no-run-if-empty docker rm'
   
These commands list the ID numbers of all the Docker containers on each host, including stopped containers and then pipes each ID to the `docker rm` command to purge.


Removing Gear Units
===================

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 gear purge
   

Removing ZFS Volumes
====================

To remove ZFS volumes created by Flocker, you will need to list the volumes on each host and then use the unique IDs in conjunction with the `zfs destroy` command.

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 'zfs list -H -o name'
   flocker   
   flocker/e16d5b2b-471d-4bbe-be23-d58bbc8f1b94.mongodb-volume-example
   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 'zfs destroy -r flocker/e16d5b2b-471d-4bbe-be23-d58bbc8f1b94.mongodb-volume-example'
   

.. _`on the Flocker development path`: https://github.com/ClusterHQ/flocker/issues/682
