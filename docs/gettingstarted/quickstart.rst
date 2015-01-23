============================
Getting started with Flocker
============================

.. header-hero::

   Getting started with Flocker
   
.. logo::

.. intro-text::

   Flocker lets you run microservices apps with database containers and move them around between servers. It comes in two pieces and you’ll need both.

.. contents::
   :local:

.. tutorial-step::

   Step 1: Installing Flocker CLI & Node
   =====================================

   .. parallel::

      .. mobile-label::

         Local

      .. image:: assets/img/macbook.png
         :class: center-block img-responsive

      Flocker CLI
      -----------

      +--------------------------------------------------------------------------+
      | Runs on your laptop                                                      |
      +--------------------------------------------------------------------------+
      | Uses application and deployment configuration files                      |
      +--------------------------------------------------------------------------+
      | Deploys containers to a cluster of servers                               |
      +--------------------------------------------------------------------------+

      .. general-division::
         :meta: arrow-down center-block hidden-xs hidden-sm

   .. parallel::

      .. mobile-label::

         Live

      .. image:: assets/img/nodes.png
         :class: center-block offset-top img-responsive

      Flocker Node
      ------------

      +--------------------------------------------------------------------------+
      | Runs on each server in a cluster                                         |
      +--------------------------------------------------------------------------+
      | Links, ports and volumes work across hosts                               |
      +--------------------------------------------------------------------------+
      | After deployment, containers can move around                             |
      +--------------------------------------------------------------------------+

      .. general-division::
         :meta: arrow-down center-block

   .. parallel::

      .. mobile-label::

         Local


      Installation
      ------------

      .. tabs::

         OS X
         ^^^^

         Install the flocker-cli client on your Mac (requires homebrew):

         .. code-block:: console

            $ brew update && \
              brew tap clusterhq/flocker && \
              brew install flocker-0.3.2

         Linux
         ^^^^^

         Install the flocker-cli client on your Linux machine:

         .. code-block:: console

            $ virtualenv flocker-tutorial && \
              flocker-tutorial/bin/pip install --upgrade pip && \
              flocker-tutorial/bin/pip install --quiet flocker-cli

      .. general-division::
         :meta: arrow-down center-block invisible

   .. parallel::

      .. mobile-label::

         Local


      Installation
      ------------

      .. tabs::

         Vagrant
         ^^^^^^^

         Simulate a flocker cluster with virtual machines on your laptop (requires Vagrant, VirtualBox):

         .. code-block:: console

            $ git clone \
              https://github.com/clusterhq/vagrant-flocker && \
              cd vagrant-flocker && \
              vagrant up

         AWS
         ^^^

         Please see our separate `AWS install instructions <http://docs.clusterhq.com/en/latest/gettingstarted/installation.html#using-amazon-web-services>`_ to get started.


      .. general-division::
         :meta: arrow-down arrow-offset center-block

.. tutorial-step-condensed::

   Step 2: Deploying a demo app
   ============================

   You should have flocker-cli installed on your laptop and flocker-node installed on some servers: either VMs on your laptop, or real instances on cloud infrastructure.
   Now you can try our simple tutorial: a Python web application and a Redis server.

   .. code-block:: console

      $ git clone https://github.com/clusterhq/flocker-tutorial
      $ cd flocker-tutorial

   fig.yml
   -------

   .. code-block:: yaml

      web:
        image: lmarsden/flask:v0.16
        links:
         - "redis:redis"
        ports:
         - "80:80"
      redis:
        image: dockerfile/redis
        ports:
         - "6379:6379"
        volumes: ["/data"]


   deployment-node1.yml
   --------------------

   .. code-block:: yaml

      "version": 1
      "nodes":
        "172.16.255.250": ["web", "redis"]
        "172.16.255.251": []


   The fig.yml describes your distributed application. The deployment.yml describes which containers to deploy where.
   If you are using real servers on AWS, you'll need to change the IP addresses in the deployment file.

   .. code-block:: console

      $ flocker-deploy deployment-node1.yml fig.yml

   Now load http://172.16.255.250/ in a web browser or the external IP of one of your AWS nodes. It works!


   ---------------------------------------------
   
   .. general-division::
      :meta: arrow-hr arrow-down center-block

.. tutorial-step-condensed::

   Step 3: Migrating a container
   =============================

   Now we are going to use a different depoyment config to show moving the Redis container with its data volume.

   deployment-node2.yml
   --------------------

   .. code-block:: yaml

      "version": 1
      "nodes":
        "172.16.255.250": ["web"]
        "172.16.255.251": ["redis"]

   .. code-block:: console

      $ flocker-deploy deployment-node2.yml app.yml

   .. image:: assets/img/migration.png
      :class: img-responsive

   In just a few seconds, you'll see that the Redis container is migrated to the other host, network traffic is re-routed, and your application is still online on both IPs!

