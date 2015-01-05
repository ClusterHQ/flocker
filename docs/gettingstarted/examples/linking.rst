:tocdepth: 1

==================
Linking Containers
==================

.. This section is tested in flocker.acceptance.test_linking.LinkingTests.
   Reflect any relevant changes here in those tests.

``Elasticsearch``, ``Logstash`` & ``Kibana``
============================================

Flocker provides functionality similar to `Docker Container Linking`_.
In this example you will learn how to deploy ``ElasticSearch``, ``Logstash``, and ``Kibana`` with Flocker, demonstrating how applications running in separate Docker containers can be linked together such that they can connect to one another, even when they are deployed on separate nodes.

The three applications are connected as follows:

* ``Logstash`` receives logged messages and relays them to ``ElasticSearch``.
* ``ElasticSearch`` stores the logged messages in a database.
* ``Kibana`` connects to ``ElasticSearch`` to retrieve the logged messages and present them in a web interface.

Create the Virtual Machines
===========================

You can reuse the Virtual Machines defined in the Vagrant configuration for :doc:`the MongoDB tutorial <../tutorial/index>`.
If you have since shutdown or destroyed those VMs, boot them up again:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ vagrant up
   Bringing machine 'node1' up with 'virtualbox' provider...
   ==> node1: Importing base box 'clusterhq/flocker-dev'...

Deploy on Node1
===============

Download and save the following configuration files to your ``flocker-tutorial`` directory:

:download:`elk-application.yml`

.. literalinclude:: elk-application.yml
   :language: yaml

:download:`elk-deployment.yml`

.. literalinclude:: elk-deployment.yml
   :language: yaml

Run ``flocker-deploy`` to start the three applications:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy elk-deployment.yml elk-application.yml
   alice@mercury:~/flocker-tutorial$

Connect to ``Kibana``
=====================

Browse to port 80 on Node1 (http://172.16.255.250:80) with your web browser.
You should see the ``Kibana`` web interface but there won't be any messages yet.

.. image:: elk-example-kibana-empty.png
   :alt: The Kibana web interface shows that in the last day there have been no events.


Generate Sample Log Messages
============================

Use ``telnet`` to connect to the ``Logstash`` service running in the Virtual Machine and send some sample ``JSON`` data.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ telnet 172.16.255.250 5000
   {"firstname": "Joe", "lastname": "Bloggs"}
   {"firstname": "Fred", "lastname": "Bloggs"}
   ^]

   telnet> quit
   Connection closed.
   alice@mercury:~/flocker-tutorial$

Now refresh the ``Kibana`` web interface and you should see those messages.

.. image:: elk-example-kibana-messages.png
   :alt: The Kibana web interface shows that there have been two events in the last five minutes.


Move ``ElasticSearch`` to Node2
===============================

Download and save the following configuration files to the ``flocker-tutorial`` directory:

.. literalinclude:: elk-deployment-moved.yml
   :language: yaml

Then run ``flocker-deploy`` to move the ``Elasticsearch`` application along with its data to the new destination host:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy elk-deployment.yml elk-application.yml
   alice@mercury:~/flocker-tutorial$

Now verify that the ``ElasticSearch`` application has moved to the other VM:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.251 docker ps
   CONTAINER ID        IMAGE                                 COMMAND                CREATED             STATUS              PORTS                              NAMES
   894d1656b74d        clusterhq/elasticsearch:latest   /bin/sh -c 'source /   2 minutes ago       Up 2 minutes        9300/tcp, 0.0.0.0:9200->9200/tcp   elasticsearch
   alice@mercury:~/flocker-tutorial$

And is no longer running on the original host:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 docker ps
   CONTAINER ID        IMAGE                            COMMAND                CREATED             STATUS              PORTS                    NAMES
   abc5c08557d4        clusterhq/kibana:latest     /usr/bin/twistd -n w   45 minutes ago      Up 45 minutes       0.0.0.0:80->8080/tcp     kibana
   44a4ee72d9ab        clusterhq/logstash:latest   /bin/sh -c /usr/loca   45 minutes ago      Up 45 minutes       0.0.0.0:5000->5000/tcp   logstash
   alice@mercury:~/flocker-tutorial$

Now if you refresh the ``Kibana`` web interface, you should see the log messages that were logged earlier.

This concludes the ``Elasticsearch-Logstash-Kibana`` example.
Read more about linking containers in our :doc:`Configuring Flocker <../../advanced/configuration>` documentation.

.. _`Docker Container Linking`: http://docs.docker.com/userguide/dockerlinks/
