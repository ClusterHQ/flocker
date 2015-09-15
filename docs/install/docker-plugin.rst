
====================================
Installing the Flocker Docker Plugin
====================================

On Ubuntu 14.04
===============

First install Flocker on some hosts.
These instructions assume you have followed the :ref:`official Flocker install instructions <installing-flocker>`.

On the same machine where you ran ``flocker-ca`` while installing Flocker, :ref:`generate a new API user certificate and key <generate-api>` for a user named ``plugin``.
Upload these files to :file:`/etc/flocker/plugin.key` and :file:`/etc/flocker/plugin.crt` on the hosts where you want to run the Flocker Docker plugin.

Then perform the following instructions on each of the hosts where you want to install the Flocker Docker plugin.

#. Install Docker 1.8 or later.

   The following command will install the latest version available:

   .. prompt:: bash $

      wget -qO- https://get.docker.com/ | sudo sh

   On Ubuntu, it's best to ensure that Docker is using the ``AUFS`` storage driver.
   The easiest way to do this is to add a ``-s aufs`` option to the :file:`/etc/default/docker` file.
   For example::
   
      DOCKER_OPTS="-s aufs"

#. Install the Flocker Docker plugin.

   On each of your container agent servers, install the Flocker plugin:

   .. prompt:: bash $

      sudo apt-get install -y python-pip build-essential libssl-dev libffi-dev python-dev
      sudo pip install git+https://github.com/clusterhq/flocker-docker-plugin.git

#. Set up init scripts to run plugin on boot.

   You need to define some configuration which will make it into the environment of the plugin:

   .. prompt:: bash $

      FLOCKER_CONTROL_SERVICE_BASE_URL=https://your-control-service:4523/v1
      MY_NETWORK_IDENTITY=1.2.3.4

   Replace ``your-control-service`` with the hostname of the control service you specified when you created your cluster.
   Replace ``1.2.3.4`` with the IP address of the host you are installing on (if your public and private IPs differ, it is generally best to use the *private* IP address of your hosts).

   Write out up an upstart script to automatically start the Flocker plugin on boot, including the configuration we just wrote out::

    $ sudo su -
    # cat <<EOF > /etc/init/flocker-docker-plugin.conf
    # flocker-docker-plugin - flocker-docker-plugin job file
    description "Flocker Plugin service"
    author "ClusterHQ <support@clusterhq.com>"
    respawn
    env FLOCKER_CONTROL_SERVICE_BASE_URL=${FLOCKER_CONTROL_SERVICE_BASE_URL}
    env MY_NETWORK_IDENTITY=${MY_NETWORK_IDENTITY}
    exec flocker-docker-plugin
    EOF
    # service flocker-docker-plugin restart

#. Now you should have the Flocker plugin running on this node, try running:

   .. prompt:: bash $

      docker run -ti -v test:/data --volume-driver=flocker busybox sh

If all is well, the plugin is able to communicate with the Flocker control service, and the agents running on the hosts are able to interact with the underlying storage, then you should see the dataset ``test`` show up in the Flocker :ref:`CLI <labs-volumes-cli>` or the :ref:`GUI <labs-volumes-gui>`.

Known limitations
=================

If the volume exists on a different host and is currently being used by a container, the Flocker plugin does not stop it being migrated out from underneath the running container.
