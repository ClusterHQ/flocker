:tocdepth: 1

===========================
Example: Linking Containers
===========================

Flocker-0.1.2 introduces support for `Docker Container Linking`_.
In this example you will learn how to deploy ``ElasticSearch``, ``Logstash``, and ``Kibana`` with Flocker, demonstrating how applications running in separate Docker containers can be linked together such that they can connect to one another, even when they are deployed on separate nodes.

The three applications are connected as follows:

* ``Logstash`` receives logged messages and relays them to ``ElasticSearch``.
* ``ElasticSearch`` stores the logged messages in a database.
* ``Kibana`` connects to ``ElasticSearch`` to retrieve the logged messages and present them in a web interface.

Download the Docker Images
==========================

In this step we will prepare the nodes by downloading all the required Docker images.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh -t root@172.16.255.250 docker pull clusterhq/elasticsearch
   ...
   alice@mercury:~/flocker-tutorial$ ssh -t root@172.16.255.250 docker pull clusterhq/logstash
   ...
   alice@mercury:~/flocker-tutorial$ ssh -t root@172.16.255.250 docker pull clusterhq/kibana
   ...
   alice@mercury:~/flocker-tutorial$

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh -t root@172.16.255.251 docker pull clusterhq/elasticsearch
   ...
   alice@mercury:~/flocker-tutorial$ ssh -t root@172.16.255.251 docker pull clusterhq/logstash
   ...
   alice@mercury:~/flocker-tutorial$ ssh -t root@172.16.255.251 docker pull clusterhq/kibana
   ...
   alice@mercury:~/flocker-tutorial$


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

Browse to port 80 on node1 (http://172.16.255.250) with your web browser.
You should see the ``Kibana`` web interface but there won't be any messages yet.

.. image:: elk-example-kibana-empty.png


Generate Sample Log Messages
============================

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ telnet 172.16.255.250 5000
   {"firstname": "Joe", "lastname": "Bloggs"}
   {"firstname": "Fred", "lastname": "Bloggs"}
   ^]

   telnet> quit
   Connection closed.
   alice@mercury:~/flocker-tutorial$

Now refresh the ``Kibana`` web interface and you should see those messages.

.. image:: elk-example-kibana-messages1.png


Move ``ElasticSearch`` to Node2
===============================

.. literalinclude:: elk-deployment-moved.yml
   :emphasize-lines: 4
   :language: yaml

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ flocker-deploy elk-deployment.yml elk-application.yml
   alice@mercury:~/flocker-tutorial$

If you refresh the ``Kibana`` web interface, you should see the log messages that were logged earlier.

Read more about linking containers in our :doc:`Configuring Flocker <../../advanced/configuration>` documentation.

.. _`Docker Container Linking`: http://docs.docker.com/userguide/dockerlinks/
