.. _flocker-containers:

=============================
Running Flocker in Containers
=============================

For some environments, such as CoreOS, and ECS you must install Flocker inside a container.

.. warning::
   Installing Flocker in containers is useful for environments such as CoreOS, or Amazon ECS, but please note that doing so is currently experimental.

You can find the relevant Docker Hub images here:

* `Dataset Agent <https://hub.docker.com/r/clusterhq/flocker-dataset-agent/>`_
* `Container Agent <https://hub.docker.com/r/clusterhq/flocker-container-agent/>`_
* `Control Service <https://hub.docker.com/r/clusterhq/flocker-control-service/>`_
* `Docker Plugin <https://hub.docker.com/r/clusterhq/flocker-docker-plugin/>`_

Before you install Flocker in containers, you must have generated the cluster certificate and key, any node certificates and keys, and API certificates and keys for the Docker plugin.

In the example commands below, certificates are assumed to live in :file:`/etc/flocker` on each node.

For more information on generating certificates, please see  :ref:`authentication`. 

Before you begin, you will need to make sure port ``4523`` is available for the control API, and port ``4524`` is available for agent nodes.

Use the following steps to install Flocker using Docker containers:

#. Run the Control Service:

   * Run the following command on one of the hosts to create a volume for the control service configuration state to live in so it remains past the container lifecycle:

     .. prompt:: bash $

        docker run --name=flocker-control-volume -v /var/lib/flocker clusterhq/flocker-control-service true
	 
   * Run the following command on the same host to start the control-service:

     .. prompt:: bash $

        docker run --restart=always -d --net=host -v /etc/flocker:/etc/flocker --volumes-from=flocker-control-volume --name=flocker-control-service clusterhq/flocker-control-service

#. Run the following commands to enable the agent service:

   .. prompt:: bash $

      docker run --restart=always -d --net=host --privileged -v /etc/flocker:/etc/flocker -v /var/run/docker.sock:/var/run/docker.sock --name=flocker-container-agent clusterhq/flocker-container-agent

   .. prompt:: bash $

      docker run --restart=always -d --net=host --privileged -v /flocker:/flocker -v /:/host -v /etc/flocker:/etc/flocker -v /dev:/dev --name=flocker-dataset-agent clusterhq/flocker-dataset-agent


#. Run the following command where you want to be able to run the Docker ``--volume-driver=flocker`` command, this will start Flocker's Docker plugin:

   * ``Control-Service-Host-DNS-or-IP`` is your control service host.
   * ``Host-IP-Address`` is the current hosts local IP address.

   .. prompt:: bash $

      docker run --restart=always -d --net=host -e FLOCKER_CONTROL_SERVICE_BASE_URL=<Control-Service-Host-DNS-or-IP>:4523/v1 -e MY_NETWORK_IDENTITY=<Host-IP-Address> -v /etc/flocker:/etc/flocker -v /run/docker:/run/docker --name=flocker-docker-plugin clusterhq/flocker-docker-plugin

Example
=======

Here is an example of a Flocker node, running all the Flocker services in containers.

.. prompt:: bash $

    # docker ps
    CONTAINER ID        IMAGE                               COMMAND                  CREATED             STATUS              PORTS                        NAMES
    2c09fcb11e80        clusterhq/flocker-docker-plugin     "flocker-docker-plugi"   2 seconds ago       Up 1 seconds                                     flocker-docker-plugin
    47ee43d887d1        clusterhq/flocker-control-service   "/usr/sbin/flocker-co"   48 minutes ago      Up 48 minutes                                    flocker-control-service
    46710d9165f0        clusterhq/flocker-dataset-agent     "/tmp/wrap_dataset_ag"   51 minutes ago      Up 51 minutes                                    flocker-dataset-agent
    e168c6f728a2        clusterhq/flocker-container-agent   "/usr/sbin/flocker-co"   53 minutes ago      Up 53 minutes                                    flocker-container-agent


Logs
====

Run the following to get the logs of the Flocker services:

.. prompt:: bash $

    docker logs flocker-control-service
    docker logs flocker-container-agent
    docker logs flocker-dataset-agent
    docker logs flocker-docker-plugin

Conclusion
==========

This should help those interested in running Flocker in environments where it is only suitable for containers to run services.

Again, this is experimental so you may run into issues. If you do, get in touch on our Freenode IRC ``#clusterhq`` or `the Flocker Google group`_.

.. _the Flocker Google group: https://groups.google.com/forum/#!forum/flocker-users
