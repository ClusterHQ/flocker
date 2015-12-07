.. _flocker-containers:

=============================
Running Flocker in Containers
=============================

The :ref:`Flocker Installer <labs-installer>` allows you install Flocker in a variety of environments.
For some of these environments, such as CoreOS, you can actually install Flocker inside a container.

.. note::
   Installing Flocker in containers is useful for environments such as CoreOS, RancherOS, or Amazon ECS, but please note that doing so is currently experimental.

You can find the relevant Docker Hub images here:

* `Dataset Agent <https://hub.docker.com/r/clusterhq/flocker-dataset-agent/>`_
* `Container Agent <https://hub.docker.com/r/clusterhq/flocker-container-agent/>`_
* `Control Service <https://hub.docker.com/r/clusterhq/flocker-control-service/>`_
* `Docker Plugin <https://hub.docker.com/r/clusterhq/flocker-docker-plugin/>`_

Before you install flocker using containers, it assumes all authentication has been setup. This means that you should have the cluster certificate and key, node certificates and keys, and API certificates and keys ready to go before following the below instructions. Please refer to `Configuring Authentication <https://docs.clusterhq.com/en/latest/config/configuring-authentication.html>`_. 

If you have your certificates in ``/etc/flocker/`` you can use the following commands to install Flocker using Docker containers.

On the hosts your running the Flocker containers, first run:

.. prompt:: bash $

    echo > /tmp/flocker-command-log

Then run the Container Agent and Dataset Agent

.. prompt:: bash $

    docker run --restart=always -d --net=host --privileged -v /etc/flocker:/etc/flocker -v /var/run/docker.sock:/var/run/docker.sock --name=flocker-container-agent clusterhq/flocker-container-agent

    docker run --restart=always -d --net=host --privileged -e DEBUG=1 -v /tmp/flocker-command-log:/tmp/flocker-command-log -v /flocker:/flocker -v /:/host -v /etc/flocker:/etc/flocker -v /dev:/dev --name=flocker-dataset-agent clusterhq/flocker-dataset-agent


Where you want to be able to run the Docker ``--volume-driver=flocker`` command you should also run the below command where ``Control-Service-Host-DNS-or-IP`` is your control service host and ``Host-IP-Address`` is the current hosts local IP address.

.. prompt:: bash $

    docker run --restart=always -d --net=host --privileged -e FLOCKER_CONTROL_SERVICE_BASE_URL=<Control-Service-Host-DNS-or-IP>:4523/v1 -e MY_NETWORK_IDENTITY=<Host-IP-Address> -v /etc/flocker:/etc/flocker -v /run/docker:/run/docker --name=flocker-docker-plugin clusterhq/flocker-docker-plugin

Then on one of the hosts run the Control Service

.. prompt:: bash $

    docker run --name=flocker-control-volume -v /var/lib/flocker clusterhq/flocker-control-service true

    docker run --restart=always -d --net=host -v /etc/flocker:/etc/flocker --volumes-from=flocker-control-volume --name=flocker-control-service clusterhq/flocker-control-service

Make sure port ``4523`` is available for the control API and ``4524`` is available for agent nodes.

What you should see
===================

Here is an example of a Flocker node running all the Flocker services in containers.

.. prompt:: bash $

    # docker ps
    CONTAINER ID        IMAGE                               COMMAND                  CREATED             STATUS              PORTS                        NAMES
    2c09fcb11e80        clusterhq/flocker-docker-plugin     "flocker-docker-plugi"   2 seconds ago       Up 1 seconds                                     flocker-docker-plugin
    47ee43d887d1        clusterhq/flocker-control-service   "/usr/sbin/flocker-co"   48 minutes ago      Up 48 minutes                                    flocker-control-service
    46710d9165f0        clusterhq/flocker-dataset-agent     "/tmp/wrap_dataset_ag"   51 minutes ago      Up 51 minutes                                    flocker-dataset-agent
    e168c6f728a2        clusterhq/flocker-container-agent   "/usr/sbin/flocker-co"   53 minutes ago      Up 53 minutes                                    flocker-container-agent


Logs
====

You can get the logs of the Flocker services by running ``docker logs <container>``

.. prompt:: bash $

    docker logs flocker-control-service


Conclusion
==========

This should help those interested in running Flocker in environments where it is only suitable for containers to run services. Again, this is experimental so you may run into issues.
