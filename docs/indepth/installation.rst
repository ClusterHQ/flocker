==================
Installing Flocker
==================

As a user of Flocker you will need to install the ``flocker-cli`` package which provides command line tools to control the cluster.
This should be installed on a machine with SSH credentials to control the cluster nodes
(e.g., if you use our Vagrant setup then the machine which is running Vagrant).

There is also a ``clusterhq-flocker-node`` package which is installed on each node in the cluster.
It contains the ``flocker-changestate``, ``flocker-reportstate``, and ``flocker-volume`` utilities.
These utilities are called by ``flocker-deploy`` (via SSH) to install and migrate Docker containers and their data volumes.

.. note:: The ``clusterhq-flocker-node`` package is pre-installed by the :doc:`Vagrant configuration in the tutorial <./tutorial/vagrant-setup>`.

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :doc:`../gettinginvolved/contributing`.

.. _installing-flocker-cli:

Installing ``flocker-cli``
==========================

Linux
-----

Before you install ``flocker-cli`` you will need a compiler, Python 2.7, and the ``virtualenv`` Python utility installed.

On CentOS 7 or Fedora 20 you can install these by running:

.. prompt:: bash alice@mercury:~$

   sudo yum install gcc python python-devel python-virtualenv

On Ubuntu or Debian you can run:

.. prompt:: bash alice@mercury:~$

   sudo apt-get install gcc python2.7 python-virtualenv python2.7-dev

Then run the following script to install ``flocker-cli``:

:version-download:`linux-install.sh.template`

.. version-literalinclude:: linux-install.sh.template
   :language: sh

Save the script to a file and then run it:

.. code-block:: console

   alice@mercury:~$ sh linux-install.sh
   ...
   alice@mercury:~$

The ``flocker-deploy`` command line program will now be available in ``flocker-tutorial/bin/``:

.. version-code-block:: console

   alice@mercury:~$ cd flocker-tutorial
   alice@mercury:~/flocker-tutorial$ bin/flocker-deploy --version
   |latest-installable|
   alice@mercury:~/flocker-tutorial$

If you want to omit the prefix path you can add the appropriate directory to your ``$PATH``.
You'll need to do this every time you start a new shell.

.. version-code-block:: console

   alice@mercury:~/flocker-tutorial$ export PATH="${PATH:+${PATH}:}${PWD}/bin"
   alice@mercury:~/flocker-tutorial$ flocker-deploy --version
   |latest-installable|
   alice@mercury:~/flocker-tutorial$

OS X
----

Install the `Homebrew`_ package manager.

Make sure Homebrew has no issues:

.. code-block:: console

   alice@mercury:~$ brew doctor
   ...
   alice@mercury:~$

Fix anything which ``brew doctor`` recommends that you fix by following the instructions it outputs.

Add the ``ClusterHQ/tap`` tap to Homebrew and install ``flocker``:

.. task:: test_homebrew flocker-|latest-installable|
   :prompt: alice@mercury:~$

You can see the Homebrew recipe in the `homebrew-tap`_ repository.

The ``flocker-deploy`` command line program will now be available:

.. version-code-block:: console

   alice@mercury:~$ flocker-deploy --version
   |latest-installable|
   alice@mercury:~$

.. _Homebrew: http://brew.sh
.. _homebrew-tap: https://github.com/ClusterHQ/homebrew-tap

.. _installing-flocker-node:

Installing ``clusterhq-flocker-node``
=====================================

There are a number of ways to install Flocker.

These easiest way to get Flocker going is to use our vagrant configuration.

- :ref:`Vagrant <vagrant-install>`

It is also possible to deploy Flocker in the cloud, on a number of different providers.

- :ref:`Using Amazon Web Services <aws-install>`
- :ref:`Using DigitalOcean <digitalocean-install>`
- :ref:`Using Rackspace <rackspace-install>`

It is also possible to install Flocker on any Fedora 20, CentOS 7, or Ubuntu 14.04 machine.

- :ref:`Installing on Fedora 20 <fedora-20-install>`
- :ref:`Installing on CentOS 7 <centos-7-install>`
- :ref:`Installing on Ubuntu 14.04 <ubuntu-14.04-install>`


.. _vagrant-install:

Vagrant
-------

The easiest way to get Flocker going on a cluster is to run it on local virtual machines using the :doc:`Vagrant configuration in the tutorial <./tutorial/vagrant-setup>`.
You can therefore skip this section unless you want to run Flocker on a cluster you setup yourself.

.. warning:: These instructions describe the installation of ``clusterhq-flocker-node`` on a Fedora 20 operating system.
             This is the only supported node operating system right now.


.. _aws-install:

Using Amazon Web Services
-------------------------

.. note:: If you are not familiar with EC2 you may want to `read more about the terminology and concepts <https://fedoraproject.org/wiki/User:Gholms/EC2_Primer>`_ used in this document.
          You can also refer to `the full documentation for interacting with EC2 from Amazon Web Services <http://docs.amazonwebservices.com/AWSEC2/latest/GettingStartedGuide/>`_.

#. Choose a nearby region and use the link to it below to access the EC2 Launch Wizard

   * `Asia Pacific (Singapore) <https://console.aws.amazon.com/ec2/v2/home?region=ap-southeast-1#LaunchInstanceWizard:ami=ami-6ceebe3e>`_
   * `Asia Pacific (Sydney) <https://console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#LaunchInstanceWizard:ami=ami-eba038d1>`_
   * `Asia Pacific (Tokyo) <https://console.aws.amazon.com/ec2/v2/home?region=ap-northeast-1#LaunchInstanceWizard:ami=ami-9583fd94>`_
   * `EU (Ireland) <https://console.aws.amazon.com/ec2/v2/home?region=eu-west-1#LaunchInstanceWizard:ami=ami-a5ad56d2>`_
   * `South America (Sao Paulo) <https://console.aws.amazon.com/ec2/v2/home?region=sa-east-1#LaunchInstanceWizard:ami=ami-2345e73e>`_
   * `US East (Northern Virginia) <https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#LaunchInstanceWizard:ami=ami-21362b48>`_
   * `US West (Northern California) <https://console.aws.amazon.com/ec2/v2/home?region=us-west-1#LaunchInstanceWizard:ami=ami-f8f1c8bd>`_
   * `US West (Oregon) <https://console.aws.amazon.com/ec2/v2/home?region=us-west-2#LaunchInstanceWizard:ami=ami-cc8de6fc>`_

#. Configure the instance

   Complete the configuration wizard; in general the default configuration should suffice.
   However, we do recommend at least the ``m3.large`` instance size.

   If you wish to customize the instance's security settings make sure to permit SSH access both from the intended client machine (for example, your laptop) and from any other instances on which you plan to install ``clusterhq-flocker-node``.
   The ``flocker-deploy`` CLI requires SSH access to the Flocker nodes to control them and Flocker nodes need SSH access to each other for volume data transfers.

   .. warning::

      Keep in mind that (quite reasonably) the default security settings firewall off all ports other than SSH.
      E.g. if you run the tutorial you won't be able to access MongoDB over the Internet, nor will other nodes in the cluster.
      You can choose to expose these ports but keep in mind the consequences of exposing unsecured services to the Internet.
      Links between nodes will also use public ports but you can configure the AWS VPC to allow network connections between nodes and disallow them from the Internet.

#. Add the *Key* to your local key chain (download it from the AWS web interface first if necessary):

   .. prompt:: bash yourlaptop$

      mv ~/Downloads/my-instance.pem ~/.ssh/
      chmod 600 ~/.ssh/my-instance.pem
      ssh-add ~/.ssh/my-instance.pem

#. Look up the public DNS name or public IP address of the new instance and, depending on the OS, log in as user "fedora", "centos", or "ubuntu" e.g.:

   .. prompt:: bash yourlaptop$

      ssh fedora@ec2-AA-BB-CC-DD.eu-west-1.compute.amazonaws.com

#. Allow SSH access for the ``root`` user, then log out.

   .. task:: install_ssh_key
      :prompt: [fedora@aws]$

#. Log back into the instances as user "root", e.g.:

   .. prompt:: bash yourlaptop$

      ssh root@ec2-AA-BB-CC-DD.eu-west-1.compute.amazonaws.com

#. Upgrade the Kernel

   Kernels older than ``3.16.4`` have a bug that affects Flocker's use of ZFS.

   .. task:: upgrade_kernel
      :prompt: [root@aws]#

   And now reboot the machine to make use of the new kernel.

   .. prompt:: bash [root@aws]#

         shutdown -r now

#. Update the SELinux policies.

   Old SELinux policies stop docker from starting containers.

   .. task:: upgrade_selinux
      :prompt: [root@aws]#


#. Follow the :ref:`generic Fedora 20 installation instructions <fedora-20-install>` below.


.. _digitalocean-install:

Using DigitalOcean
------------------

Another way to get a Flocker cluster running is to use DigitalOcean.
You'll probably want to setup at least two nodes.

#. Create a new Droplet running Fedora 20

   * Visit https://cloud.digitalocean.com/droplets/new
   * Choose a minimum of 8GB of RAM
   * Choose the Fedora 20 x64 Linux distribution as your image
   * You may choose to add an SSH key, or DigitalOcean will email you the root SSH password

#. Look up the public IP address of the new Droplet, and SSH in

   You can find the IP in the Droplet page after it is created, to the left of the green "Active" text near the top.

   .. code-block:: sh

      yourlaptop$ ssh root@203.0.113.109

#. Install a supported Linux kernel

   Kernels older than ``3.16.4`` have a bug that affects Flocker's use of ZFS.
   To switch to the newest kernel, follow these steps:

   #. Configure the Droplet to boot with the desired kernel:

      * Go to the DigitalOcean control panel for your specific Droplet, and in the Settings section choose the Kernel tab.
      * Choose the newest kernel for Fedora 20 (scroll all the way to the bottom) and press "Change".

        At the time of writing, the latest supported kernel is |digitalocean_kernel_title|.

   #. Upgrade the kernel package inside the virtual machine:

      The selected kernel may no-longer be available from the standard Fedora 20 repositories, so we install from ``koji``.

      .. task:: install_digitalocean_kernel
         :prompt: [root@digitalocean]#

   #. Power Cycle the Droplet

      Droplet kernel changes only take effect after *power cycling* the virtual machine.

      * Shut down the virtual machine:

      .. code-block:: sh

         [root@digitalocean]# shutdown -h now

      * On the "Power" administration page, click "Boot".


#. Follow the :ref:`generic Fedora 20 installation instructions <fedora-20-install>` below.


.. _rackspace-install:

Using Rackspace
---------------

Another way to get a Flocker cluster running is to use Rackspace.
You'll probably want to setup at least two nodes.

#. Create a new Cloud Server running Fedora 20

   * Visit https://mycloud.rackspace.com
   * Click "Create Server".
   * Choose the Fedora 20 Linux distribution as your image.
   * Choose a Flavor. We recommend at least "8 GB General Purpose v1".
   * Add your SSH key

#. SSH in

   You can find the IP in the Server Details page after it is created.

   .. code-block:: sh

      yourlaptop$  ssh root@203.0.113.109

#. Follow the :ref:`generic Fedora 20 installation instructions <fedora-20-install>` below.

.. _fedora-20-install:

Installing on Fedora 20
-----------------------

.. note:: The following commands all need to be run as root on the machine where ``clusterhq-flocker-node`` will be running.

Flocker requires ``zfs`` which in turn requires the ``kernel-devel`` package to be installed.
Before installing ``clusterhq-flocker-node``, you need to install a version of the ``kernel-devel`` package that matches the currently running kernel.
Here is a short script to help you install the correct ``kernel-devel`` package.
Copy and paste it into a root console on the target node:

.. task:: install_kernel_devel
   :prompt: [root@node]#

.. note:: On some Fedora installations, you may find that the correct ``kernel-devel`` package is already installed.

Now install the ``clusterhq-flocker-node`` package.
To install ``clusterhq-flocker-node`` on Fedora 20 you must install the RPM provided by the ClusterHQ repository.
You must also install the ZFS package repository.
The following commands will install the two repositories and the ``clusterhq-flocker-node`` package.
Paste them into a root console on the target node:

.. task:: install_flocker_yum fedora-20
   :prompt: [root@node]#

Installing ``flocker-node`` will automatically install Docker, but the ``docker`` service may not have been enabled or started.
To enable and start Docker, run the following commands in a root console:

.. task:: enable_docker
   :prompt: [root@node]#


.. _centos-7-install:

Installing on CentOS 7
----------------------

Flocker requires the latest available kernel.

.. task:: upgrade_kernel_centos
   :prompt: [root@node]#

Flocker requires ZFS, and installing ZFS requires that the running kernel be the one that will eventually be used.
Thus we need to reboot into the new kernel.

.. prompt:: bash [root@node]#

   shutdown -r now

Now install the ``flocker-node`` package.
To install ``flocker-node`` on CentOS 7 you must install the RPM provided by the ClusterHQ repository.
You must also install the ZFS package repository.
The following commands will install the two repositories and the ``flocker-node`` package.
Paste them into a root console on the target node:

.. task:: install_flocker_yum centos-7
   :prompt: [root@node]#

Installing ``flocker-node`` will automatically install Docker, but the ``docker`` service may not have been enabled or started.
To enable and start Docker, run the following commands in a root console:

.. task:: enable_docker
   :prompt: [root@node]#


.. _ubuntu-14.04-install:

Installing on Ubuntu 14.04
--------------------------

.. To test this:
   * create two ubuntu medium instances on AWS with security group "acceptance"
   * ssh ubuntu@... for each of the node IPs
   * sudo cp .ssh/authorized_keys /root/.ssh/authorized_keys
   * ssh root@... for each of the node IPs
   * This is similar to following the AWS instructions above but ignoring the "Upgrade the Kernel" step which is different on Ubuntu and SELinux can be ignored I think

.. XXX Maybe say that it needs at least 3.16.4 instead of "latest available", but maybe not, if this is best consistent with CentOS (or change that too?)

Flocker requires the latest available kernel.

.. TODO get rid of the quotes in this task

.. task:: upgrade_kernel_ubuntu
   :prompt: [root@node]#

Flocker requires ZFS, and installing ZFS requires that the running kernel be the one that will eventually be used.
Thus we need to reboot into the new kernel.

.. prompt:: bash [root@node]#

   shutdown -r now

Flocker requires recent versions of ZFS and Docker.

.. task:: install_requirements_ubuntu
   :prompt: [root@node]#

Now install the ``clusterhq-flocker-node`` package.

.. task:: install_flocker_ubuntu
   :prompt: [root@node]#

Post installation configuration
-------------------------------

Flocker requires a ZFS pool named ``flocker``.
The following commands will create a 10 gigabyte ZFS pool backed by a file.
Paste them into a root console:

.. task:: create_flocker_pool_file
   :prompt: [root@node]#

.. note:: It is also possible to create the pool on a block device.

.. XXX: Document how to create a pool on a block device: https://clusterhq.atlassian.net/browse/FLOC-994

The Flocker command line client (``flocker-deploy``) must be able to establish an SSH connection to each node.
Additionally, every node must be able to establish an SSH connection to all other nodes.
So ensure that the firewall allows access to TCP port 22 on each node; from your IP address and from the nodes' IP addresses.
Your firewall will also need to allow access to the ports your applications are exposing.

.. warning::

   Keep in mind the consequences of exposing unsecured services to the Internet.
   Both applications with exposed ports and applications accessed via links will be accessible by anyone on the Internet.

The Flocker command line client must also be able to log into each node as user ``root``.
Add your public SSH key to the ``~/.ssh/authorized_keys`` file for the ``root`` user on each node if you haven't already done so.

You have now installed ``clusterhq-flocker-node`` and created a ZFS for it.
You have also ensured that the ``flocker-deploy`` command line tool is able to communicate with the node.

Next you may want to perform the steps in :doc:`the tutorial <./tutorial/moving-applications>` , to ensure that your nodes are correctly configured.
Replace the IP addresses in the ``deployment.yaml`` files with the IP address of your own nodes.
Keep in mind that the tutorial was designed with local virtual machines in mind, and results in an insecure environment.
