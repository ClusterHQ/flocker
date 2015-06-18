.. _labs-docker-plugin:

=====================
Flocker Docker plugin
=====================

The Flocker Docker plugin is a Docker volumes plugin, connecting Docker directly to the Flocker volumes API.

It connects Flocker to Docker via:

* The ``docker run -v name:path --volume-driver=flocker`` syntax.
* The ``VolumeDriver`` parameter on ``/containers/create`` in the Docker Remote API.

See the `Docker documentation on experimental plugins <https://github.com/docker/docker/tree/master/experimental>`_.

Using this integration, it then becomes possible to provision portable Flocker volumes directly from Docker's own orchestration and composition tools, Swarm and Compose.

It will also enable integrations with Mesosphere/Marathon and eventually Kubernetes.

See https://github.com/ClusterHQ/flocker-docker-plugin

Installation on Ubuntu 14.04
============================

First :ref:`install Flocker <labs-installer>`.

Install the experimental build of Docker:

.. prompt:: bash $

    wget -qO- https://experimental.docker.com/ | sudo sh

On each of your container agent servers (Ubuntu 14.04 or CentOS 7), install the Flocker plugin:

.. prompt:: bash $

    sudo pip install git+https://github.com/clusterhq/flocker-docker-plugin.git

We need to define some configuration which will make it into the environment of the plugin:

.. prompt:: bash $

    FLOCKER_CONTROL_SERVICE_BASE_URL=https://your-control-service:4523/v1
    MY_NETWORK_IDENTITY=1.2.3.4

Replace ``your-control-service`` with the hostname of the control service you specified :ref:`when you created your cluster <labs-installer>`.
Replace ``1.2.3.4`` with the IP address of the host you are installing on (if your public and private IPs differ, it is generally best to use the *private* IP address of your hosts).

Write out up an upstart script to automatically start the Flocker plugin on boot:

.. prompt:: bash $

    cat <<EOF > /etc/init/flocker-docker-plugin.conf
    # flocker-docker-plugin - flocker-docker-plugin job file
    description "Flocker Plugin service"
    author "ClusterHQ <support@clusterhq.com>"
    respawn
    env FLOCKER_CONTROL_SERVICE_BASE_URL=${FLOCKER_CONTROL_SERVICE_BASE_URL}
    env MY_NETWORK_IDENTITY=${MY_NETWORK_IDENTITY}
    exec flocker-docker-plugin
    EOF
    service flocker-docker-plugin restart
