.. _vagrant-setup:

========================================
Using Vagrant to Create Virtual Machines
========================================

.. note:: If you already followed these instructions from a previous Flocker release, see :ref:`upgrading-vagrant-environment`.

Before you can deploy anything with Flocker you'll need a node onto which to deploy it.
For the purpose of the :ref:`MongoDB tutorial<tutorial-mongo>`, the instructions below describe how to use `Vagrant`_ to create two `VirtualBox`_ virtual machines.

It is important to note the following:

* These virtual machines serve as hosts on which Flocker can run Docker.
* Flocker does not require Vagrant or VirtualBox.
* You can also run Flocker on other virtualization technology (VMware for example), on clouds (EC2 for example), or directly on physical hardware.
* The two virtual machines are each assigned a 10 GB virtual disk.
  The underlying disk files grow to about 5 GB, so you will need at least 10 GB of free disk space on your workstation.

These instructions include a :file:`Vagrantfile` to download, which will boot the necessary virtual machines.
Flocker and its dependencies will be installed on these virtual machines the first time you start them.

These virtual machines are statically assigned the following IPs:

* node1: ``172.16.255.250``
* node2: ``172.16.255.251``

These two IP addresses are used throughout the :ref:`MongoDB tutorial<tutorial-mongo>`.

.. warning::

   If these addresses conflict with your local network configuration, you will need to edit the :file:`Vagrantfile` to change the IP addresses.

   You will also need to generate a new set of certificates and keys using the Flocker CLI ``flocker-ca`` tool, and copy these to the virtual machines.
   
   This will also require you to start the node services manually.
   For more information, see :ref:`authentication`.

Installing Vagrant and VirtualBox
=================================

Follow the instructions specific to your platform that are provided in the `Vagrant`_ and `VirtualBox`_ documentation.

Alternatively, on OS X you can use ``brew-cask`` to install the packages using the `Homebrew`_ package manager.
For example:

.. prompt:: bash alice@mercury:~/$

   brew install caskroom/cask/brew-cask
   brew cask install virtualbox
   brew cask install vagrant

.. _creating-vagrant-VMs:

Creating Vagrant Virtual Machines for Flocker
=============================================

#. Create a tutorial directory, for example:

   .. prompt:: bash alice@mercury:~/$

      mkdir flocker-tutorial
      cd flocker-tutorial

#. Download the Vagrant configuration file by right clicking on the link below.
   Save it in the :file:`flocker-tutorial` directory, preserving the filename.

   :version-download:`Vagrantfile.template`

   .. version-literalinclude:: Vagrantfile.template
      :language: ruby
      :lines: 1-8
      :append: ...

#. Download the cluster and user credentials by right clicking on the links below.
   Save these to the :file:`flocker-tutorial` directory, also preserving the filenames.
   
   :download:`cluster.crt`
   
   :download:`user.crt`
   
   :download:`user.key`

#. Use ``vagrant up`` to start and provision the virtual machines:

   .. prompt:: bash alice@mercury:~/flocker-tutorial$ auto

      alice@mercury:~/flocker-tutorial$ vagrant up
      Bringing machine 'node1' up with 'virtualbox' provider...
      ==> node1: Importing base box 'clusterhq/flocker-dev'...
      ... lots of output ...
      ==> node2: ln -s '/usr/lib/systemd/system/docker.service' '/etc/systemd/system/multi-user.target.wants/docker.service'
      alice@mercury:~/flocker-tutorial$

   This step can take several minutes, as it downloads the Vagrant image, boots up two nodes, and downloads the Docker image necessary to run the :ref:`MongoDB tutorial<tutorial-mongo>`.
   The time this takes will depend on your network connectivity and CPU speed.
   Fortunately this extra work is only necessary the first time you bring up a node (until you destroy it).

#. After ``vagrant up`` completes you may want to verify that the two virtual machines are really running and accepting SSH connections:

   .. prompt:: bash alice@mercury:~/flocker-tutorial$ auto

      alice@mercury:~/flocker-tutorial$ vagrant status
      Current machine states:

      node1                     running (virtualbox)
      node2                     running (virtualbox)
      ...
      alice@mercury:~/flocker-tutorial$ vagrant ssh -c hostname node1
      node1
      Connection to 127.0.0.1 closed.
      alice@mercury:~/flocker-tutorial$ vagrant ssh -c hostname node2
      node2
      Connection to 127.0.0.1 closed.
      alice@mercury:~/flocker-tutorial$

#. Configure your SSH agent to allow Flocker to authenticate itself to the virtual machine:

   * If you're not sure whether you already have an SSH agent running, ``ssh-add`` can tell you.

     If you have an SSH agent running, you'll see no output.
     If you don't, you'll see an error:

     .. prompt:: bash alice@mercury:~/flocker-tutorial$ auto

        alice@mercury:~/flocker-tutorial$ ssh-add
        Could not open a connection to your authentication agent.

   * If you don't have an SSH agent running, start one:

     .. prompt:: bash alice@mercury:~/flocker-tutorial$ auto

        alice@mercury:~/flocker-tutorial$ eval $(ssh-agent)
        Agent pid 27233

   * Finally, add the Vagrant key to your agent:

     .. prompt:: bash alice@mercury:~/flocker-tutorial$

        ssh-add ~/.vagrant.d/insecure_private_key

You now have two virtual machines running and easy SSH access to them.

.. note::
   
   On some versions of Vagrant and VirtualBox, restarting the tutorial virtual machines via the ``vagrant halt`` and ``vagrant up`` commands can result in losing the static IP configuration, making the nodes unreachable on the assigned ``172.15.255.25x`` addresses.
   
   In this case you should destroy and recreate the machines with the ``vagrant destroy`` and ``vagrant up`` commands.

.. _upgrading-vagrant-environment:

Upgrading the Vagrant Environment
=================================

The :file:`Vagrantfile` used in the :ref:`MongoDB tutorial<tutorial-mongo>` installs an RPM package called ``clusterhq-flocker-node`` on both the nodes.
If you already have a tutorial environment from a previous release, you'll need to ensure that both tutorial nodes are running the latest version of ``clusterhq-flocker-node`` before continuing with the following tutorials.

#. Check the current version of Flocker on each of the nodes.

   Log into each node and run the ``flocker-dataset-agent`` command with a ``--version`` argument.

   .. prompt:: bash alice@mercury:~/flocker-tutorial$

      ssh root@172.16.255.250 flocker-dataset-agent --version

   If you find that you are running an older version of Flocker than |version|, proceed to the next step to rebuild the tutorial environment.

#. If you have an older version of ``Vagrantfile``, run ``vagrant destroy`` in the :file:`flocker-tutorial` directory:

   .. warning:: 

	  This will completely remove the existing nodes and their data.

   .. prompt:: bash alice@mercury:~/flocker-tutorial$ auto

      alice@mercury:~/flocker-tutorial$ vagrant destroy
          node2: Are you sure you want to destroy the 'node2' VM? [y/N] y
      ==> node2: Forcing shutdown of VM...
      ==> node2: Destroying VM and associated drives...
      ==> node2: Running cleanup tasks for 'shell' provisioner...
          node1: Are you sure you want to destroy the 'node1' VM? [y/N] y
      ==> node1: Forcing shutdown of VM...
      ==> node1: Destroying VM and associated drives...
      ==> node1: Running cleanup tasks for 'shell' provisioner...
      alice@mercury:~/flocker-tutorial$

#. Delete the cached SSH host keys for the virtual machines as they will change when new virtual machines are created.

   Failing to do so will cause SSH to think there is a security problem when you connect to the recreated virtual machines.

   .. prompt:: bash alice@mercury:~/flocker-tutorial$

      ssh-keygen -f "$HOME/.ssh/known_hosts" -R 172.16.255.250
      ssh-keygen -f "$HOME/.ssh/known_hosts" -R 172.16.255.251

#. Delete the original :file:`Vagrantfile` and complete the steps in :ref:`creating-vagrant-VMs` to download the latest versions of the files (:file:`Vagrantfile`, :file:`cluster.crt`, :file:`user.crt`, and :file:`user.key`) and run ``vagrant up``.

If you do not have an older versions of the :file:`Vagrantfile`, or if the ``vagrant destroy`` command fails, you can remove existing nodes `directly from VirtualBox`_.

The two virtual machines will have names like ``flocker-tutorial_node1_1410450919851_28614`` and ``flocker-tutorial_node2_1410451102837_79031``.

.. _`Vagrant`: https://docs.vagrantup.com/v2/
.. _`VirtualBox`: https://www.virtualbox.org/
.. _`directly from VirtualBox`: https://www.virtualbox.org/manual/ch01.html#idp55629568
.. _Homebrew: http://brew.sh
