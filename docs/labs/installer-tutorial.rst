.. _short-tutorial:

=================================================
Short Tutorial: Deploy and Migrate a Stateful App
=================================================

When you have completed the steps in :ref:`labs-installing-unofficial-flocker-tools` (or installed and configured Flocker via the :ref:`main instructions <installing-flocker>`), you can use the following steps to deploy a highly sophisticated stateful app to test out Flocker:

#. Begin by finding out the IP addresses of our first two nodes.
   Do this by running:

   .. prompt:: bash $

      cat cluster.yml

#. Add the public IP addresses of the first two nodes in the following commands:

   In this example, ``demo`` is the name of the Flocker volume being created, which will map onto the Flocker volume being created.

   .. prompt:: bash $

      NODE1="<node 1 public IP>"
      NODE2="<node 2 public IP>"
      KEY="<path on your machine to your .pem file>"
      chmod 0600 $KEY
      ssh -i $KEY root@$NODE1 docker run -d -v demo:/data --volume-driver=flocker --name=redis redis:latest
      ssh -i $KEY root@$NODE1 docker run -d -e USE_REDIS_HOST=redis --link redis:redis -p 80:80 --name=app binocarlos/moby-counter:latest
      uft-flocker-volumes list

   This may take up to a minute since Flocker is provisioning and attaching an volume from the storage backend for the Flocker ``demo`` volume.
   At the end you should see the volume created and attached to the first node.

#. Now visit ``http://<node 1 public IP>/`` and click around to add some Moby Docks to the screen.
   Now let's stop the containers, then start the stateful app on another node in the cluster.

   .. prompt:: bash $

      ssh -i $KEY root@$NODE1 docker rm -f app
      ssh -i $KEY root@$NODE1 docker rm -f redis
      ssh -i $KEY root@$NODE2 docker run -d -v demo:/data --volume-driver=flocker --name=redis redis:latest
      ssh -i $KEY root@$NODE2 docker run -d -e USE_REDIS_HOST=redis --link redis:redis -p 80:80 --name=app binocarlos/moby-counter:latest
      uft-flocker-volumes list

   At the end you should see the volume has moved to the second node.

   This may take up to a minute since Flocker is ensuring the volume is on the second host before starting the container.

#. Now visit ``http://<node 2 public IP>/`` and you’ll see that the location of the Moby Docks has been preserved.
   Nice.

If you now want to clean up your volumes, your instances and your local files, follow the instructions in :ref:`clean-your-cluster`.
