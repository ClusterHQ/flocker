===========
Cleaning Up
===========

Once you've followed through the tutorial, you may wish to purge the virtual machines of all containers and state created by Flocker.
This will enable you to test, play around with Flocker or repeat the tutorial process without having to destroy and rebuild the virtual machines created in the :ref:`Vagrant Setup <VagrantSetup>`.

The tutorial's virtual machines are created with IP addresses 172.16.255.250 and 172.16.255.251, so you can run the necessary cleanup commands via SSH.


Removing Containers
===================

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 'docker ps -aq | xargs --no-run-if-empty docker rm'
   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.251 'docker ps -aq | xargs --no-run-if-empty docker rm'
   
These commands list the ID numbers of all the Docker containers on each host, including stopped containers and then pipes each ID to the `docker rm` command to purge.


Removing Gear Units
===================

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 gear purge
   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.251 gear purge
   

Removing ZFS Volumes
====================

To remove ZFS volumes created by Flocker, you will need to list the volumes on each host and then use the unique IDs in conjunction with the `zfs destroy` command.

.. code-block:: console

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 'zfs list -H -o name'
   
   flocker   
   flocker/e16d5b2b-471d-4bbe-be23-d58bbc8f1b94.mongodb-volume-example
   
   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.251 'zfs list -H -o name'
   
   flocker   
   flocker/e16d5b2b-471d-4bbe-be23-d58bbc8f1b94.mongodb-volume-example

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.250 'zfs destroy -r flocker/e16d5b2b-471d-4bbe-be23-d58bbc8f1b94.mongodb-volume-example'

   alice@mercury:~/flocker-mysql$ ssh root@172.16.255.251 'zfs destroy -r flocker/e16d5b2b-471d-4bbe-be23-d58bbc8f1b94.mongodb-volume-example'

