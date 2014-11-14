==================
Installing Flocker
==================

As a user of Flocker you will need to install the ``flocker-cli`` package which provides command line tools to control the cluster.
This should be installed on a machine with SSH credentials to control the cluster nodes
(e.g., if you use our Vagrant setup then the machine which is running Vagrant).

There is also a ``flocker-node`` package which is installed on each node in the cluster.
It contains the ``flocker-changestate``, ``flocker-reportstate``, and ``flocker-volume`` utilities.
These utilities are called by ``flocker-deploy`` (via SSH) to install and migrate Docker containers and their data volumes.

.. note:: The ``flocker-node`` package is pre-installed by the :doc:`Vagrant configuration in the tutorial <./tutorial/vagrant-setup>`.

.. note:: If you're interested in developing Flocker (as opposed to simply using it) see :doc:`../gettinginvolved/contributing`.

.. _installing-flocker-cli:

Installing ``flocker-cli``
==========================

Linux
-----

Before you install ``flocker-cli`` you will need a compiler, Python 2.7, and the ``virtualenv`` Python utility installed.
On Fedora 20 you can install these by running:

.. code-block:: console

   alice@mercury:~$ sudo yum install @buildsys-build python python-devel python-virtualenv

On Ubuntu or Debian you can run:

.. code-block:: console

   alice@mercury:~$ sudo apt-get install gcc python2.7 python-virtualenv python2.7-dev

Then run the following script to install ``flocker-cli``:

:download:`linux-install.sh`

.. literalinclude:: linux-install.sh
   :language: sh

Save the script to a file and then run it:

.. code-block:: console

   alice@mercury:~$ sh linux-install.sh
   ...
   alice@mercury:~$

The ``flocker-deploy`` command line program will now be available in ``flocker-tutorial/bin/``:

.. code-block:: console

   alice@mercury:~$ cd flocker-tutorial
   alice@mercury:~/flocker-tutorial$ bin/flocker-deploy --version
   0.3.0
   alice@mercury:~/flocker-tutorial$

If you want to omit the prefix path you can add the appropriate directory to your ``$PATH``.
You'll need to do this every time you start a new shell.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ export PATH="${PATH:+${PATH}:}${PWD}/bin"
   alice@mercury:~/flocker-tutorial$ flocker-deploy --version
   0.3.0
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

Add the ``ClusterHQ/flocker`` tap to Homebrew and install ``flocker``:

.. code-block:: console

   alice@mercury:~$ brew tap ClusterHQ/tap
   ...
   alice@mercury:~$ brew install flocker-0.3.0
   ...
   alice@mercury:~$ brew test flocker-0.3.0
   ...
   alice@mercury:~$

You can see the Homebrew recipe in the `homebrew-tap`_ repository.

The ``flocker-deploy`` command line program will now be available:

.. code-block:: console

   alice@mercury:~$ flocker-deploy --version
   0.3.0
   alice@mercury:~$

.. _Homebrew: http://brew.sh
.. _homebrew-tap: https://github.com/ClusterHQ/homebrew-tap


Installing ``flocker-node``
===========================

Vagrant
-------

The easiest way to get Flocker going on a cluster is to run it on local virtual machines using the :doc:`Vagrant configuration in the tutorial <./tutorial/vagrant-setup>`.
You can therefore skip this section unless you want to run Flocker on a cluster you setup yourself.

.. warning:: These instructions describe the installation of ``flocker-node`` on a Fedora 20 operating system.
             This is the only supported node operating system right now.


Using Amazon Web Services
-------------------------

One easy way to get a Flocker cluster running is to use Amazon's EC2 service.
You'll probably want to setup at least two nodes.

.. note:: If you are not familiar with EC2 you may want to `read more about the terminology and concepts <https://fedoraproject.org/wiki/User:Gholms/EC2_Primer>`_ used in this document.
          You can also refer to `the full documentation for interacting with EC2 from Amazon Web Services <https://docs.amazonwebservices.com/AWSEC2/latest/GettingStartedGuide/>`_.

#. Choose an AMI for your EC2 Instance

   * Visit https://fedoraproject.org/en/get-fedora#clouds
   * In the EC2 **Fedora 20** section choose your local region and **64 Bit** and click the "Launch it!" button.

#. Configure the AMI

   Complete the configuration wizard; in general the default configuration should suffice.

   We recommend a ``m3.large`` instance at least.

   You will later enable SSH root login to this machine, so you may wish configure the security settings to only allow access from you IP address or network.

   .. warning::

      Keep in mind that (quite reasonably) the default security settings firewall off all ports other than SSH.
      E.g. if you run the tutorial you won't be able to access MongoDB over the Internet, nor will other nodes in the cluster.
      You can choose to expose these ports but keep in mind the consequences of exposing unsecured services to the Internet.
      Links between nodes will also use public ports, but you can configure the AWS VPC to allow network connections between nodes and disallow them from the Internet.

#. Download the Key from the AWS web interface and add it to your local key chain:

   .. code-block:: sh

      yourlaptop$ mv ~/Downloads/my-instance.pem ~/.ssh/
      yourlaptop$ chmod 600 ~/.ssh/my-instance.pem
      yourlaptop$ ssh-add ~/.ssh/my-instance.pem

#. Log in as user "fedora" to your new node's address, e.g.:

   .. code-block:: sh

      yourlaptop$ ssh fedora@ec2-54-72-149-156.eu-west-1.compute.amazonaws.com

#. Upgrade the Kernel

   The Amazon AMI includes an old kernel whose development package is no longer easily installable.

   We need the kernel-devel package in order to install the ZFS modules, so first we do a system upgrade.

   .. code-block:: sh

      [fedora@aws]$ sudo yum upgrade

   The upgrade doesn't make the new kernel default. Let's do that now.

   .. code-block:: sh

      [fedora@aws]$ sudo grubby --set-default-index 0

   And now reboot the machine to make use of the new kernel.

   .. code-block:: sh

      [fedora@aws]$ sudo shutdown -r now

#. Allow SSH access for the ``root`` user

   Remove the various restrictions in the ``/root/.authorized_keys`` file on your node, anything before ``ssh-rsa`` in the following example:

   .. code-block:: sh

      [fedora@aws]$ sudo cat /root/.ssh/authorized_keys
      no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="echo 'Please login as the user \"fedora\" rather than the user \"root\".';echo;sleep 10" ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCe6FJDenfTF23azfJ2OVaorp3AsRQzdDlgkx/j0LrvQVyh95yMKL1GwVKuk8mlMGUEQiKImU6++CzTPu5zB2fpX+P5NrRZyBrokwp2JMQQD8lOqvvF7hw5bq2+8D8pYz11HkfEt9m5CVhLc1lt57WYnAujeRgaUhy9gql6r9ZI5aE8a3dpzxjP6S22er1/1dfLbecQaVM3cqpZVA6oAm8I6kJFyjiK6roRpaB2GTXTdpeGGiyYh8ATgDfyZPkWhKfpEGF5xJtsKSS+kFrHNqfqzDiVFv6R3fVS3WhdrC/ClqI941GeIM7PoDm3+KWlnaHJrjBX1N6OEBS8iEsj+24D username


   You should now be able to log in as "root" and the ``authorized_keys`` file should look approximately like this:

   .. code-block:: sh

      yourlaptop$ ssh root@ec2-54-72-149-156.eu-west-1.compute.amazonaws.com
      [root@aws]# cat /root/.ssh/authorized_keys
      ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCe6FJDenfTF23azfJ2OVaorp3AsRQzdDlgkx/j0LrvQVyh95yMKL1GwVKuk8mlMGUEQiKImU6++CzTPu5zB2fpX+P5NrRZyBrokwp2JMQQD8lOqvvF7hw5bq2+8D8pYz11HkfEt9m5CVhLc1lt57WYnAujeRgaUhy9gql6r9ZI5aE8a3dpzxjP6S22er1/1dfLbecQaVM3cqpZVA6oAm8I6kJFyjiK6roRpaB2GTXTdpeGGiyYh8ATgDfyZPkWhKfpEGF5xJtsKSS+kFrHNqfqzDiVFv6R3fVS3WhdrC/ClqI941GeIM7PoDm3+KWlnaHJrjBX1N6OEBS8iEsj+24D username

#. Follow the generic Fedora 20 installation instructions below.


Fedora 20
---------

.. note:: The following commands all need to be run as root on the machine where ``flocker-node`` will be running.

Flocker requires ``zfs`` which in turn requires the ``kernel-devel`` package to be installed.
Before installing ``flocker-node``, you need to install a version of the ``kernel-devel`` package that matches the currently running kernel.
Here is a short script to help you install the correct ``kernel-devel`` package.
Copy and paste it into a root console on the target node:

.. code-block:: sh

  UNAME_R=$(uname -r)
  PV=${UNAME_R%.*}
  KV=${PV%%-*}
  SV=${PV##*-}
  ARCH=$(uname -m)
  yum install -y https://kojipkgs.fedoraproject.org/packages/kernel/${KV}/${SV}/${ARCH}/kernel-devel-${UNAME_R}.rpm

Now install the ``flocker-node`` package.
To install ``flocker-node`` on Fedora 20 you must install the RPM provided by the ClusterHQ repository.
You must also install the ZFS package repository.
The following commands will install the two repositories and the ``flocker-node`` package.
Paste them into a root console on the target node:

.. code-block:: sh

   yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm
   yum install -y http://archive.clusterhq.com/fedora/clusterhq-release$(rpm -E %dist).noarch.rpm
   yum install -y flocker-node

Installing ``flocker-node`` will automatically install Docker, but the ``docker`` service may not have been enabled or started.
To enable and start Docker, run the following commands in a root console:

.. code-block:: sh

   systemctl start docker
   systemctl enable docker

Flocker requires a ZFS pool named ``flocker``.
The following commands will create a 10 gigabyte ZFS pool backed by a file.
Paste them into a root console:

.. code-block:: sh

   mkdir /opt/flocker
   truncate --size 10G /opt/flocker/pool-vdev
   zpool create flocker /opt/flocker/pool-vdev

.. note:: It is also possible to create the pool on a block device.

.. XXX: Document how to create a pool on a block device: https://clusterhq.atlassian.net/browse/FLOC-994

The Flocker command line client (``flocker-deploy``) must be able to establish an SSH connection to each node.
Additionally, every node must be able to establish an SSH connection to all other nodes.
So ensure that the firewall allows access to TCP port 22 on each node; from your IP address and from the nodes' IP addresses.
Your firewall will also need to allow access to the ports your applications are exposing.

The Flocker command line client must also be able to log into each node as user ``root``.
Add your public SSH key to the ``~/.ssh/authorized_keys`` file for the ``root`` user on each node if you haven't already done so.

You have now installed ``flocker-node`` and created a ZFS for it.
You have also ensured that the ``flocker-deploy`` command line tool is able to communicate with the node.

Next you may want to perform the steps in :doc:`the tutorial <./tutorial/moving-applications>` , to ensure that your nodes are correctly configured.
Replace the IP addresses in the ``deployment.yaml`` files with the IP address of your own nodes.
Keep in mind that the tutorial was designed with local virtual machines in mind, and results in an insecure environment.
