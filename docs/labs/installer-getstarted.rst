.. _labs-installing-unofficial-flocker-tools:

==================================
Getting Started with the Installer
==================================

#. Installing the Installer:

   First we install the installer on your workstation.
   This will work on Linux or OS X machines with Docker installed.

   * If you don't have Docker installed, install it now (`Mac <https://docs.docker.com/mac/started/>`_, `Linux  <https://docs.docker.com/linux/started/>`_).
     Check that Docker is working, for example by running:

     .. prompt:: bash $

        docker ps

     You should get a (possibly empty) list of running containers on your machine.

   * Then install the installer, which will pull the Docker image:

     .. prompt:: bash $

        curl -sSL https://get.flocker.io/ | sh

     This assumes that your user can use ``sudo``, and may prompt you for your password.
     This installer is a tiny script which puts some wrapper scripts (around ``docker run`` commands) into your :file:`/usr/local/bin`.

   * Now test one of the installed tools:

     .. prompt:: bash $

        uft-flocker-ca --version

     This should return something like ``1.5.0``, showing you which version of the Flocker Client is installed.

#. Make a local directory for your cluster files:

   The tools will create some configuration files and certificate files for your cluster.
   It is convenient to keep these in a directory, so let's make a directory on your workstation like this:

   .. prompt:: bash $

      mkdir -p ~/clusters/test
      cd ~/clusters/test

   Now we'll put some files in this directory.

#. Get some nodes:

   So now let's use the tools we've just installed to deploy and configure a Flocker cluster.

   * Run the following command in your :file:`~/clusters/test` directory you made earlier:

     .. prompt:: bash $

        mkdir terraform
        vim terraform/terraform.tfvars

     .. note::

        In the following step, do not use a key (:file:`.pem` file) which is protected by a passphrase.
        If necessary, generate and download a new keypair in the EC2 console.

   * Now paste the following variables into your :file:`terraform.tfvars` file::

        # AWS keys
        aws_access_key = "your AWS access key"
        aws_secret_key = "your AWS secret key"

        # AWS region and zone
        aws_region = "region you want nodes deployed in e.g. us-east-1"
        aws_availability_zone = "zone you want nodes deployed in e.g. us-east-1a"

        # Key to authenticate to nodes via SSH
        aws_key_name = "name of EC2 keypair"
        private_key_path = "private key absolute path on machine running installer"

        # Instance types and number of nodes; total = agent_nodes + 1 (for master)
        aws_instance_type = "m3.large"
        agent_nodes = "2"

     .. note::

        By default, the installer will launch one master node (where the Flocker control service runs) and two agent nodes (where volumes get attached and containers run).
        Please refer to the `AWS pricing guide <https://aws.amazon.com/ec2/pricing/>`_ to understand how much this will cost you.

   * Now run the following command to automatically provision some nodes.

     .. prompt:: bash $

        uft-flocker-sample-files
        uft-flocker-get-nodes --ubuntu-aws

     This step should take 30-40 seconds, and then you should see output like this::

        Apply complete! Resources: 10 added, 0 changed, 0 destroyed.

     This should have created a pre-configured :file:`cluster.yml` file in the current directory.

   Now you have some nodes, it's time to install and configure Flocker on them!

#. Install and configure Flocker:

   Run the following command:

   .. prompt:: bash $

      uft-flocker-install cluster.yml && uft-flocker-config cluster.yml && uft-flocker-plugin-install cluster.yml

   This step should take about 5 minutes, and will:

   * Install the OS packages on your nodes required to run Flocker, including Docker.
   * Configure certificates, push them to your nodes, set up firewall rules for the Flocker control service.
   * Start all the requisite Flocker services.
   * Install the Flocker plugin for Docker, so that you can control Flocker directly from the Docker CLI.

#. Check that the Flocker cluster is active:

   Try the Flocker CLI to check that all your nodes came up:

   .. prompt:: bash $

      uft-flocker-volumes list-nodes
      uft-flocker-volumes list

   You can see that there are no volumes yet.

Now that you have a Flocker cluster, if you want a short demonstration of deploying and migrating a stateful application, see our :ref:`short tutorial <short-tutorial>`.
