.. _tutorial-swarm-compose:

===================================================
Tutorial: Using Flocker with Docker, Swarm, Compose
===================================================

For this tutorial, we've provided a simple app for you to deploy, made up of two containers:

* A node.js application called ``moby-counter``.
  This app allows you to put Docker icons anywhere on your screen, and the locations are stored in a database.
* A PostgreSQL database for the application, which is stateful, and needs a Flocker volume.

You will use Docker Compose to deploy the app on a Swarm cluster using Flocker as a volume driver.

You will then move both containers from one node to another by changing the Swarm constraints in the Docker Compose file and re-deploying.
The app will keep its data!

What You'll Need
================

* A Flocker cluster with Swarm installed.

  * Use one of our :ref:`Flocker with Swarm installation options <docker-integration>` to get one.

* A Client machine with Docker Compose and access to the Swarm master.

  * If you used our :ref:`CloudFormation installer <cloudformation>` the "Client" VM is preconfigured with Docker Compose, so use the following command to ssh into Compose:

    .. prompt:: bash $

        ssh -i <YourKey> ubuntu@<ClientIP>

    ``<YourKey>`` is the path to the key you downloaded from AWS.
   
    ``<ClientIP>`` is the Client IP you got from the CloudFormation Outputs tab.
	
    By using the CloudFormation installer, the rest of this tutorial will assume you are logged into the Client node.

  * Alternatively, install `Docker Compose <https://docs.docker.com/compose/install/>`_ on any machine which has network access to the Swarm master that you created when you installed Swarm.

Step 1: Set ``DOCKER_HOST``
===========================

Compose uses the environment variable ``DOCKER_HOST`` to know how to talk to the Swarm master.
If you used our :ref:`CloudFormation installer <cloudformation>`, it is listed in the Outputs tab of your CloudFormation stack.

Use the following commmand to set the ``DOCKER_HOST`` environment variable:

.. prompt:: bash $

   export DOCKER_HOST=<SwarmMaster>

``<SwarmMaster>`` is the address of your Swarm master, in the format ``ip:port``.
For example, ``1.2.3.4:2376``.

Step 2: Deploy the app on the first node
========================================

The two Docker Compose files below need to be saved on your Client machine, in a directory named :file:`swarm-compose-tutorial`.

:download:`tutorial-downloads/flocker-swarm-tutorial-node1.yml`

:download:`tutorial-downloads/flocker-swarm-tutorial-node2.yml`

You can either click the cloud icons to save the files locally, and then move them onto your Client machine using using a transfer medium such as SSH, SCP or SFTP, or right click each file, and copy the link address and run the following commands with the tutorial URLs:

.. prompt:: bash $

    mkdir swarm-compose-tutorial
    cd swarm-compose-tutorial
    wget <Tutorial1Url>
    wget <Tutorial2Url>

.. TODO: It would be much nicer if we had a Sphinx directive to output the URL of a download, so the user didn't have to right click and copy-paste here.

The Docker Compose files both have the same layout, as illustrated below, except the ``node2`` file has ``constraint:flocker-node==2`` instead of ``node==1``.

.. literalinclude:: tutorial-downloads/flocker-swarm-tutorial-node1.yml
   :language: yaml

* The ``moby-counter`` app container is exposed on port 80.
* The app is configured with the same database credentials as the database.
* The ``postgres`` container uses a ``volume_driver`` of ``flocker`` and uses a named Flocker volume called ``postgres``.

  * Flocker will automatically provision this volume on-demand if it doesn't already exist.

Step 2.1: Optionally specify size and profile
---------------------------------------------

If you want to specify a size or a profile for the volume before creating it, run the following:

.. prompt:: bash $

   docker volume create -d flocker -o size=10G -o profile=bronze --name=postgres

.. TODO link to a page documenting how to configure volume hub keys

.. note::

   At this point if you gave the cluster a Volume Hub key, check the `Volume Hub <https://volumehub.clusterhq.com>`_ and you should be able to see the volume created but not used by any containers yet.

Otherwise the volume will be automatically provisioned with default size (75G) and profile (silver) when you do ``docker-compose up`` below.

Step 2.2: Deploying the app
---------------------------

Now deploy the app by running:

.. prompt:: bash $

   docker-compose -f flocker-swarm-tutorial-node1.yml up -d

.. note::

   At this point in the `Volume Hub <https://volumehub.clusterhq.com>`_ and you should be able to see the volume in use by the ``postgres`` container.

Open ``http://<FlockerNode1IP>/`` in a browser, and click around to add some Docker logos on the screen.
The locations of the logos get stored (persisted) in the PostgreSQL database, and saved to the Flocker volume.

Step 3: Move the app
====================

Now we will demonstrate stopping the app on one machine and starting it on the other.


.. prompt:: bash $

   docker-compose -f flocker-swarm-tutorial-node1.yml rm -f
   docker-compose -f flocker-swarm-tutorial-node2.yml up -d

Note that we are destroying the first set of containers and then starting the second compose file which has the constraint to force Swarm to schedule the containers onto the second node.

Flocker will detach and attach the storage so that the container starts up with the expected data.

.. note::

   At this point in the `Volume Hub <https://volumehub.clusterhq.com>`_ and you should be able to see the volume being moved from node 1 to node 2 and the new container being started up.

Open ``http://<FlockerNode2IP>/`` in a browser, and you'll be able to see that your data has persisted!

Cleaning up
===========

To clean up, run:

.. prompt:: bash $

   docker-compose -f flocker-swarm-tutorial-node2.yml rm -f
   flockerctl destroy postgres

Note that this will delete the ``postgres`` volume.

To understand why we need to use ``flockerctl`` to destroy the volume, see the :ref:`concepts-docker-integration` section.

Next steps
==========

Now try deploying your own Docker Compose app!

* Set ``volume_driver: flocker`` for any stateful containers you have.
* Specify the Flocker volumes using ``volume: "flocker_volume_name:/path_inside_container"`` syntax.

Or, try one of our other :ref:`Docker Tutorials <docker-tutorials>`.

Notes
=====

Because we do not have a networking solution in this example, we use Swarm constraints to force both containers to be on the same node each time we deploy them so that regular Docker links work.
