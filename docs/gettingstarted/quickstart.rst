:layout: homepage

============================
Getting started with Flocker
============================

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

      .. image:: images/macbook.png
         :class: center-block img-responsive
         :alt: Flocker CLI diagram

      Flocker CLI
      -----------

      +--------------------------------------------------------------------------+
      | Runs on your laptop                                                      |
      +--------------------------------------------------------------------------+
      | Uses application and deployment configuration files                      |
      +--------------------------------------------------------------------------+
      | Deploys containers to a cluster of servers                               |
      +--------------------------------------------------------------------------+

      .. empty-div:: arrow-down center-block hidden-xs hidden-sm

   .. parallel::

      .. mobile-label::

         Live

      .. image:: images/nodes.png
         :class: center-block offset-top img-responsive
         :alt: Flocker Node diagram

      Flocker Node
      ------------

      +--------------------------------------------------------------------------+
      | Runs on each server in a cluster                                         |
      +--------------------------------------------------------------------------+
      | Links, ports and volumes work across hosts                               |
      +--------------------------------------------------------------------------+
      | After deployment, containers can move around                             |
      +--------------------------------------------------------------------------+

      .. empty-div:: arrow-down center-block

   .. parallel::

      .. mobile-label::

         Local


      Installation
      ------------

      .. noscript-content::
      
         OS X
         ^^^^

         Install the flocker-cli client on your Mac (requires Homebrew):

         .. code-block:: console

            $ brew update && \
              brew tap clusterhq/flocker && \
              brew install flocker-0.3.2
            
      .. noscript-content::

         Ubuntu / Debian
         ^^^^^^^^^^^^^^^

         Install the dependencies:
         
         .. code-block:: console
         
            $ sudo apt-get install gcc python2.7 python-virtualenv python2.7-dev

         Next, install the flocker-cli client on your Linux machine:

         .. code-block:: console

            $ virtualenv flocker-tutorial && \
              flocker-tutorial/bin/pip install --upgrade pip && \
              flocker-tutorial/bin/pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-0.3.2-py2-none-any.whl

         Fedora 20
         ^^^^^^^^^

         Install the dependencies:
         
         .. code-block:: console
         
            $ sudo yum install @buildsys-build python python-devel python-virtualenv
         
         Next, install the flocker-cli client on your Linux machine:

         .. code-block:: console

            $ virtualenv flocker-tutorial && \
              flocker-tutorial/bin/pip install --upgrade pip && \
              flocker-tutorial/bin/pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-0.3.2-py2-none-any.whl


      .. tabs::

         Ubuntu / Debian
         ^^^^^^^^^^^^^^^

         Install the dependencies:
         
         .. code-block:: console
         
            $ sudo apt-get install gcc python2.7 python-virtualenv python2.7-dev

         Next, install the flocker-cli client on your Linux machine:

         .. code-block:: console

            $ virtualenv flocker-tutorial && \
              flocker-tutorial/bin/pip install --upgrade pip && \
              flocker-tutorial/bin/pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-0.3.2-py2-none-any.whl

         Fedora 20
         ^^^^^^^^^

         Install the dependencies:
         
         .. code-block:: console
         
            $ sudo yum install @buildsys-build python python-devel python-virtualenv
         
         Next, install the flocker-cli client on your Linux machine:

         .. code-block:: console

            $ virtualenv flocker-tutorial && \
              flocker-tutorial/bin/pip install --upgrade pip && \
              flocker-tutorial/bin/pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-0.3.2-py2-none-any.whl

         OS X
         ^^^^

         Install the flocker-cli client on your Mac (requires Homebrew):

         .. code-block:: console

            $ brew update && \
              brew tap clusterhq/flocker && \
              brew install flocker-0.3.2

      .. empty-div:: arrow-down center-block invisible

   .. parallel::

      .. mobile-label::

         Live


      Installation
      ------------

      .. noscript-content::

         Vagrant
         ^^^^^^^

         Simulate a Flocker cluster with virtual machines on your laptop (requires Vagrant, VirtualBox):

         .. code-block:: console

            $ git clone \
              https://github.com/clusterhq/vagrant-flocker && \
              cd vagrant-flocker && \
              vagrant up

         AWS
         ^^^

         Please see our separate `AWS install instructions <http://docs.clusterhq.com/en/latest/gettingstarted/installation.html#using-amazon-web-services>`_ to get started.

      .. tabs::

         Vagrant
         ^^^^^^^

         Simulate a Flocker cluster with virtual machines on your laptop (requires Vagrant, VirtualBox):

         .. code-block:: console

            $ git clone \
              https://github.com/clusterhq/vagrant-flocker && \
              cd vagrant-flocker && \
              vagrant up

         AWS
         ^^^

         Please see our separate `AWS install instructions <http://docs.clusterhq.com/en/latest/gettingstarted/installation.html#using-amazon-web-services>`_ to get started.


      .. empty-div:: arrow-down arrow-offset center-block

.. tutorial-step::

   Step 2: Deploying a demo app
   ============================
   
   .. tutorial-step-condensed::

      You should have flocker-cli installed on your laptop and flocker-node installed on some servers: either VMs on your laptop, or real instances on cloud infrastructure.
      Now you can try our simple tutorial: a Python web application and a Redis server.

      .. code-block:: console

         $ git clone https://github.com/clusterhq/flocker-quickstart
         $ cd flocker-quickstart

      fig.yml
      -------

      .. code-block:: yaml

         web:
           image: clusterhq/flask
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


      The fig.yml describes your distributed application.
      The deployment.yml describes which containers to deploy where.
      If you are using real servers on AWS, you'll need to change the IP addresses in the deployment file.

      .. code-block:: console

         $ flocker-deploy deployment-node1.yml fig.yml

      Now load http://172.16.255.250/ in a web browser or the external IP of one of your AWS nodes.
      It works!


   ---------------------------------------------
   
   .. empty-div:: arrow-hr arrow-down center-block

.. tutorial-step::

   Step 3: Migrating a container
   =============================
   
   .. tutorial-step-condensed::

      Now we are going to use a different deployment configuration to show moving the Redis container with its data volume.

      deployment-node2.yml
      --------------------

      .. code-block:: yaml

         "version": 1
         "nodes":
           "172.16.255.250": ["web"]
           "172.16.255.251": ["redis"]

      .. code-block:: console

         $ flocker-deploy deployment-node2.yml fig.yml

      .. image:: images/migration.png
         :class: img-responsive img-spaced
         :alt: Flocker migration diagram

      In just a few seconds, you'll see that the Redis container is migrated to the other host, network traffic is re-routed, and your application is still online on both IPs!

