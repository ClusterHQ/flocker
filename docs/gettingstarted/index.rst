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

      .. tabs::

         OS X
         ^^^^

         Install the Flocker client on your Mac (requires Homebrew):

         .. task:: test_homebrew flocker-|latest-installable|
            :prompt: you@laptop:~$

         Ubuntu 14.04
         ^^^^^^^^^^^^

         Install the Flocker client on your Linux machine:

         .. task:: install_cli ubuntu-14.04
            :prompt: you@laptop:~$

         Fedora 20
         ^^^^^^^^^

         Install the Flocker client on your Linux machine:

         .. version-code-block:: console

            you@laptop:~$ sudo yum install -y @buildsys-build python python-devel python-virtualenv libffi-devel openssl-devel && \
              curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/linux-install.sh && \
              sh linux-install.sh && \
              source flocker-tutorial/bin/activate

      .. noscript-content::

         OS X
         ^^^^

         Install the Flocker client on your Mac (requires Homebrew):

         .. task:: test_homebrew flocker-|latest-installable|
            :prompt: you@laptop:~$

         Ubuntu 14.04
         ^^^^^^^^^^^^

         Install the Flocker client on your Linux machine:

         .. task:: install_cli ubuntu-14.04
            :prompt: you@laptop:~$

         Fedora 20
         ^^^^^^^^^

         Install the Flocker client on your Linux machine:

         .. version-code-block:: console

            you@laptop:~$ sudo yum install -y @buildsys-build python python-devel python-virtualenv libffi-devel openssl-devel && \
              curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/linux-install.sh && \
              sh linux-install.sh && \
              source flocker-tutorial/bin/activate

      .. empty-div:: arrow-down center-block invisible

   .. parallel::

      Installation
      ------------

      .. mobile-label::

         Live

      .. tabs::

         Vagrant
         ^^^^^^^

         Simulate a Flocker cluster with virtual machines on your laptop (requires `Vagrant <http://www.vagrantup.com/downloads>`_, `VirtualBox <https://www.virtualbox.org/wiki/Downloads>`_):

         .. version-code-block:: console

            you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/Vagrantfile && \
              curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/cluster.crt && \
              curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/user.crt && \
              curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/user.key && \
              vagrant up && \
              [ -e "${SSH_AUTH_SOCK}" ] || eval $(ssh-agent) && \
              ssh-add ~/.vagrant.d/insecure_private_key

         AWS
         ^^^

         Please see our separate :ref:`AWS install instructions <aws-install>` to get started.

      .. noscript-content::

         .. The noscript content must come after the tabs, because the prompt
            command defines CSS styles on the first use of a prompt. See FLOC-2104.

         Vagrant
         ^^^^^^^

         Simulate a Flocker cluster with virtual machines on your laptop (requires `Vagrant <http://www.vagrantup.com/downloads>`_, `VirtualBox <https://www.virtualbox.org/wiki/Downloads>`_):

         .. version-code-block:: console

            you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/Vagrantfile && \
              curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/cluster.crt && \
              curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/user.crt && \
              curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/user.key && \            
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

      .. container:: hidden

         .. Create the files to be downloaded with curl, but don't show download links for them

         :download:`fig.yml`
         :download:`deployment-node1.yml`
         :download:`deployment-node2.yml`

      .. version-code-block:: console

         you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/fig.yml
         you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/deployment-node1.yml
         you@laptop:~$ curl -O https://docs.clusterhq.com/en/|latest-installable|/_downloads/deployment-node2.yml

      fig.yml
      -------

      .. literalinclude:: fig.yml
         :language: yaml

      deployment-node1.yml
      --------------------

      .. literalinclude:: deployment-node1.yml
         :language: yaml

      The ``fig.yml`` file describes your distributed application.
      The ``deployment-node1.yml`` file describes which containers to deploy where.
      If you are using real servers on AWS, you'll need to change the IP addresses in the deployment file.

      .. code-block:: console

         you@laptop:~$ flocker-deploy 172.16.255.250 deployment-node1.yml fig.yml

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

      .. literalinclude:: deployment-node2.yml
         :language: yaml

      .. code-block:: console

         you@laptop:~$ flocker-deploy 172.16.255.250 deployment-node2.yml fig.yml

      .. image:: images/migration.png
         :class: img-responsive img-spaced
         :alt: Flocker migration diagram

      In just a few seconds, you'll see that the Redis container is migrated to the other host, network traffic is re-routed, and your application is still online on both IPs!
