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

Before you install Flocker in containers, all authentication must be completed.
This means that you will have generated the cluster certificate and key, the  node certificates and keys, and the API certificates and keys.

In the example commands below, certificates are assumed to live in :file:`/etc/flocker` but other environments may choose to create containers that hold certificates and configuration and share amongst the Flocker service containers.
The latter is not documented.

For more information on generating certificates, please see  :ref:`authentication`. 

Before you begin, you will need to make sure port ``4523`` is available for the control API and port ``4524`` is available for agent nodes.

Use the following steps to install Flocker using Docker containers:

#. Run the following commands on one of the hosts to run the Control Service, the first command will create a volume for the control service configuration state to live in so it remains past the container lifecycle, the second command will start the control-service:

   .. prompt:: bash $

      docker run --name=flocker-control-volume -v /var/lib/flocker clusterhq/flocker-control-service true

   .. prompt:: bash $

      docker run --restart=always -d --net=host -v /etc/flocker:/etc/flocker --volumes-from=flocker-control-volume --name=flocker-control-service clusterhq/flocker-control-service

#. Run the Container agent:

   .. prompt:: bash $

      docker run --restart=always -d --net=host --privileged -v /etc/flocker:/etc/flocker -v /var/run/docker.sock:/var/run/docker.sock --name=flocker-container-agent clusterhq/flocker-container-agent

#. Run the Dataset agent:

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


Conclusion
==========

This should help those interested in running Flocker in environments where it is only suitable for containers to run services.

Again, this is experimental so you may run into issues.
