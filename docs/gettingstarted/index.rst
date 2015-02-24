:layout: homepage

============================
Getting started with Flocker
============================

.. logo::

.. intro-text::

   Flocker lets you run microservices apps with database containers and move them around between servers.
   It comes in two pieces and you'll need both.

.. contents::
   :local:

.. tutorial-step::

   Step 1: Installing Flocker Client & Node
   ========================================

   .. parallel::

      .. mobile-label::

         Local

      .. image:: images/macbook.png
         :class: center-block img-responsive
         :alt: Flocker Client diagram

      Flocker Client
      --------------

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

      Installation
      ------------

      .. mobile-label::

         Local

      .. noscript-content::

         OS X
         ^^^^

         Install the Flocker client on your Mac (requires Homebrew):

         .. version-code-block:: console

            you@laptop:~$ brew update && \
              brew tap clusterhq/flocker && \
              brew install flocker-|latest-installable|

      .. noscript-content::

         Ubuntu / Debian
         ^^^^^^^^^^^^^^^

         Install the Flocker client on your Linux machine:

         .. version-code-block:: console

            you@laptop:~$ sudo apt-get update && sudo apt-get install -y gcc python2.7 python-virtualenv python2.7-dev && \
              virtualenv flocker-tutorial && \
              flocker-tutorial/bin/pip install --upgrade pip && \
              flocker-tutorial/bin/pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-|latest-installable|-py2-none-any.whl && source flocker-tutorial/bin/activate

         Fedora 20
         ^^^^^^^^^

         Install the Flocker client on your Linux machine:

         .. version-code-block:: console

            you@laptop:~$ sudo yum install -y @buildsys-build python python-devel python-virtualenv && \
              virtualenv flocker-tutorial && \
              flocker-tutorial/bin/pip install --upgrade pip && \
              flocker-tutorial/bin/pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-|latest-installable|-py2-none-any.whl && source flocker-tutorial/bin/activate


      .. tabs::

         OS X
         ^^^^

         Install the Flocker client on your Mac (requires Homebrew):

         .. version-code-block:: console

            you@laptop:~$ brew update && \
              brew tap clusterhq/flocker && \
              brew install flocker-|latest-installable|

         Ubuntu / Debian
         ^^^^^^^^^^^^^^^

         Install the Flocker client on your Linux machine:

         .. version-code-block:: console

            you@laptop:~$ sudo apt-get update && sudo apt-get install -y gcc python2.7 python-virtualenv python2.7-dev && \
              virtualenv flocker-tutorial && \
              flocker-tutorial/bin/pip install --upgrade pip && \
              flocker-tutorial/bin/pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-|latest-installable|-py2-none-any.whl && source flocker-tutorial/bin/activate

         Fedora 20
         ^^^^^^^^^

         Install the Flocker client on your Linux machine:

         .. version-code-block:: console

            you@laptop:~$ sudo yum install -y @buildsys-build python python-devel python-virtualenv && \
              virtualenv flocker-tutorial && \
              flocker-tutorial/bin/pip install --upgrade pip && \
              flocker-tutorial/bin/pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-|latest-installable|-py2-none-any.whl && source flocker-tutorial/bin/activate

      .. empty-div:: arrow-down center-block invisible

   .. parallel::

      Installation
      ------------

      .. mobile-label::

         Live

      .. noscript-content::

         Vagrant
         ^^^^^^^

         Simulate a Flocker cluster with virtual machines on your laptop (requires `Vagrant <http://www.vagrantup.com/downloads>`_, `VirtualBox <https://www.virtualbox.org/wiki/Downloads>`_):

         .. code-block:: console

            you@laptop:~$ git clone \
              https://github.com/clusterhq/vagrant-flocker && \
              cd vagrant-flocker && \
              vagrant up && \
              [ -e "${SSH_AUTH_SOCK}" ] || eval $(ssh-agent) && \
              ssh-add ~/.vagrant.d/insecure_private_key

         AWS
         ^^^

         Please see our separate :ref:`AWS install instructions <aws-install>` to get started.

      .. tabs::

         Vagrant
         ^^^^^^^

         Simulate a Flocker cluster with virtual machines on your laptop (requires `Vagrant <http://www.vagrantup.com/downloads>`_, `VirtualBox <https://www.virtualbox.org/wiki/Downloads>`_):

         .. code-block:: console

            you@laptop:~$ git clone \
              https://github.com/clusterhq/vagrant-flocker && \
              cd vagrant-flocker && \
              vagrant up && \
              [ -e "${SSH_AUTH_SOCK}" ] || eval $(ssh-agent) && \
              ssh-add ~/.vagrant.d/insecure_private_key

         AWS
         ^^^

         Please see our separate :ref:`AWS install instructions <aws-install>` to get started.


      .. empty-div:: arrow-down arrow-offset center-block

.. tutorial-step::

   Step 2: Deploying a demo app
   ============================

   .. tutorial-step-condensed::

      You should have the Flocker client installed on your laptop and flocker-node installed on some servers: either VMs on your laptop, or real instances on cloud infrastructure.
      Now you can try our simple tutorial: a Python web application and a Redis server.

      .. code-block:: console

         you@laptop:~$ git clone https://github.com/clusterhq/flocker-quickstart
         you@laptop:~$ cd flocker-quickstart

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

         you@laptop:~$ flocker-deploy deployment-node1.yml fig.yml

      Now load http://172.16.255.250/ in a web browser or the external IP of one of your AWS nodes.
      It works!


   ---------------------------------------------

   .. empty-div:: arrow-hr arrow-down center-block

.. tutorial-step::

   Step 3: Migrating a container
   =============================

   .. tutorial-step-condensed::

      Now we are going to use a different deployment configuration to show moving the Redis container with its data volume.
      The web server will remain deployed on the first host and remain accessible via either host's address.

      deployment-node2.yml
      --------------------

      .. code-block:: yaml

         "version": 1
         "nodes":
           "172.16.255.250": ["web"]
           "172.16.255.251": ["redis"]

      .. code-block:: console

         you@laptop:~$ flocker-deploy deployment-node2.yml fig.yml

      .. image:: images/migration.png
         :class: img-responsive img-spaced
         :alt: Flocker migration diagram

      In just a few seconds, you'll see that the Redis container is migrated to the other host, network traffic is re-routed, and your application is still online on both IPs!
