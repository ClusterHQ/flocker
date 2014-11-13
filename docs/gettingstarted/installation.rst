==================
Installing Flocker
==================

As a user of Flocker you will need to install the ``flocker-cli`` package which provides command line tools to control the cluster.
This should be installed on a machine with SSH credentials to control the cluster nodes
(e.g., if you use our Vagrant setup then the machine which is running Vagrant).

There is also a ``flocker-node`` package which is installed on each node in the cluster.
It contains the ``flocker-changestate``, ``flocker-reportstate``, and ``flocker-volume`` utilities.
These utilities are called by ``flocker-deploy`` (via SSH) to install and migrate Docker containers and their data volumes.

.. note:: For now the ``flocker-node`` package is pre-installed by the :doc:`Vagrant configuration in the tutorial <./tutorial/vagrant-setup>`.

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


Prepare an Amazon Web Services EC2 Instance
===========================================

Launch a Fedora20 EC2 instance and install ZFS in preparation for installing Flocker.

.. note:: If you are not familiar with EC2 you can read more about the terminology and concepts: http://fedoraproject.org/wiki/User:Gholms/EC2_Primer
          And full documentation for interacting with EC2 is available from Amazon Web Services: http://docs.amazonwebservices.com/AWSEC2/latest/GettingStartedGuide/

#. Choose an AMI for your EC2 Instance

   * Visit the EC2 Dashboard page and click "Launch Instance"
   * Choose a Fedora20 AMI from the "Community AMIs" section

     OR

   * Visit http://fedoraproject.org/en/get-fedora#clouds
   * Choose Fedora20 and your local region and click the "Launch it!" button.


  E.g.

  ::

  Fedora-x86_64-20-20140407-sda (ami-a5ad56d2)

  Description:
  Official Fedora AMI - Fedora-x86_64-20-20140407-sda

#. Configure the AMI

   Complete the 7 step configuration wizard.

   You will need at least:
   * XXX GB RAM
   * XXX GB Storage
   * XXX CPU

   We recommend the following settings:
   * XXX

   You will later enable root login to this machine, so we recommend that you configure the security settings to only allow access from you IP address or network.

#. Download the Key and add it to your key chain

   .. code-block:: sh

   mv ~/Downloads/my-instance.pem ~/.ssh/
   chmod 600 ~/.ssh/my-instance.pem
   ssh-add ~/.ssh/my-instance.pem

#. Log in as user "fedora"

   .. code-block::

      ssh fedora@ec2-54-72-149-156.eu-west-1.compute.amazonaws.com

#. Upgrade the Kernel

   The Amazon AMI includes an old kernel whose development package is no longer easily installable.

   We need the kernel-devel package in order to install the ZFS modules, so first we do a system upgrade.

   .. code-block:: sh
      yum upgrade

   The upgrade doesn't make the new kernel default. Let's do that now.

   .. code-block:: sh

   grubby --set-default-index 0

   And now reboot the machine to make use of the new kernel.

   .. code-block:: sh

      shutdown -r now

#. Install ZFS Repo

   See https://github.com/ClusterHQ/flocker/pull/967

   The new kernel / dkms are incompatible with the stable zfsonlinux package.
   So for now, we add the clusterhq repo which has zfs + dkms Tom's package fixes

   .. code-block:: sh
      yum install -y https://storage.googleapis.com/archive.clusterhq.com/fedora/clusterhq-release$(rpm -E %dist).noarch.rpm

#. Install the ClusterHQ omnibus package Repo

   .. code-block::

      sudo tee /etc/yum.repos.d/clusterhq-build.repo
      [clusterhq-build]
      name=clusterhq-build
      baseurl=http://build.staging.clusterhq.com/results/omnibus/sumo-package-508/fedora20/
      gpgcheck=0
      enabled=1

#. Install ``flocker-node``

   .. code-block::

      sudo yum install clusterhq-flocker-node


   .. code-block::

      ...

      Installing : spl-dkms-0.6.3-1.1.fc20.noarch                                                                                                   53/62
      Loading new spl-0.6.3 DKMS files...
      /usr/lib/dkms/common.postinst: line 123: which: command not found
      Building for 3.11.10-301.fc20.x86_64
      Module build for kernel 3.11.10-301.fc20.x86_64 was skipped since the
      kernel source for this kernel does not seem to be installed.
        Installing : zfs-dkms-0.6.3-1.1.fc20.noarch                                                                                                   54/62
      Loading new zfs-0.6.3 DKMS files...
      /usr/lib/dkms/common.postinst: line 123: which: command not found
      Building for 3.11.10-301.fc20.x86_64
      Module build for kernel 3.11.10-301.fc20.x86_64 was skipped since the
      kernel source for this kernel does not seem to be installed.

      ...


   .. code-block::

      $ flocker-reportstate --version
      0.3.0-536-gcfaef23

#. Allow SSH access for the ``root`` user

   Remove the "Please login as..." login message below...

   .. code-block::

      cat ~/.ssh/authorized_keys
      no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="echo 'Please login as the user \"fedora\" rather than the user \"root\".';echo;sleep 10" ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCe6FJDenfTF23azfJ2OVaorp3AsRQzdDlgkx/j0LrvQVyh95yMKL1GwVKuk8mlMGUEQiKImU6++CzTPu5zB2fpX+P5NrRZyBrokwp2JMQQD8lOqvvF7hw5bq2+8D8pYz11HkfEt9m5CVhLc1lt57WYnAujeRgaUhy9gql6r9ZI5aE8a3dpzxjP6S22er1/1dfLbecQaVM3cqpZVA6oAm8I6kJFyjiK6roRpaB2GTXTdpeGGiyYh8ATgDfyZPkWhKfpEGF5xJtsKSS+kFrHNqfqzDiVFv6R3fVS3WhdrC/ClqI941GeIM7PoDm3+KWlnaHJrjBX1N6OEBS8iEsj+24D FLOC-983


   You should now be able to log in as "root" and the ``authorized_keys`` file should look like this:

   .. code-block::

      ssh root@ec2-54-72-149-156.eu-west-1.compute.amazonaws.com cat .ssh/authorized_keys
      ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCe6FJDenfTF23azfJ2OVaorp3AsRQzdDlgkx/j0LrvQVyh95yMKL1GwVKuk8mlMGUEQiKImU6++CzTPu5zB2fpX+P5NrRZyBrokwp2JMQQD8lOqvvF7hw5bq2+8D8pYz11HkfEt9m5CVhLc1lt57WYnAujeRgaUhy9gql6r9ZI5aE8a3dpzxjP6S22er1/1dfLbecQaVM3cqpZVA6oAm8I6kJFyjiK6roRpaB2GTXTdpeGGiyYh8ATgDfyZPkWhKfpEGF5xJtsKSS+kFrHNqfqzDiVFv6R3fVS3WhdrC/ClqI941GeIM7PoDm3+KWlnaHJrjBX1N6OEBS8iEsj+24D FLOC-983

#. Test a minimal deployment

   Follow the tutorial, but substitute the IP addresses with those of your new EC2 instance.

   .. note:: You will find the Public IP address of your EC2 instance by clicking its row in the "Instances" dashboard.
             The IP address will be "Description" tab.

   E.g.

   .. code-block:: yaml

      $ cat minimal-deployment.yml
      "version": 1
      "nodes":
      "54.72.149.156": ["mongodb-example"]
