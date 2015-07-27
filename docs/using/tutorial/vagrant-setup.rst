.. _tutvagrant:

================
Before You Begin
================

Requirements
============

To replicate the steps demonstrated in this tutorial, you will need:

* Linux, FreeBSD, or OS X
* `Vagrant`_ (1.6.2 or newer)
* `VirtualBox`_
* At least 10GB disk space available for the two virtual machines
* The OpenSSH client (the ``ssh``, ``ssh-agent``, and ``ssh-add`` command-line programs)
* bash
* The ``mongo`` MongoDB interactive shell (see below for installation instructions)

You will also need ``flocker-cli`` installed (providing the ``flocker-deploy`` command).
See :ref:`installing-flocker-cli`.

.. note:: If you already have a version of ``flocker-cli`` older than |version| installed, delete the install script and directory before installing the latest version.

Setup
=====

Installing MongoDB
------------------

The MongoDB client can be installed through the various package managers for Linux, FreeBSD and OS X.
If you do not already have the client on your machine, you can install it by running the appropriate command for your system.

Ubuntu
^^^^^^

.. code-block:: console

   alice@mercury:~$ sudo apt-get install mongodb-clients
   ...
   alice@mercury:~$

Red Hat / Fedora
^^^^^^^^^^^^^^^^

.. code-block:: console

   alice@mercury:~$ sudo yum install mongodb
   ...
   alice@mercury:~$

OS X
^^^^

Install `Homebrew`_

.. code-block:: console

   alice@mercury:~$ brew update
   ...
   alice@mercury:~$ brew install mongodb
   ...
   alice@mercury:~$

Other Systems
^^^^^^^^^^^^^

See the official `MongoDB installation guide`_ for your system.

.. _vagrant-setup:

Creating Vagrant VMs Needed for Flocker
---------------------------------------

.. note:: If you already have a tutorial environment from a previous release see :ref:`upgrading-vagrant-environment`.

Before you can deploy anything with Flocker you'll need a node onto which to deploy it.
To make this easier, this tutorial uses `Vagrant`_ to create two VirtualBox VMs.

These VMs serve as hosts on which Flocker can run Docker.
Flocker does not require Vagrant or VirtualBox.
You can run it on other virtualization technology (e.g., VMware), on clouds (e.g., EC2), or directly on physical hardware.

For your convenience, this tutorial includes ``Vagrantfile`` which will boot the necessary VMs.
Flocker and its dependencies will be installed on these VMs the first time you start them.
One important thing to note is that these VMs are statically assigned the IPs ``172.16.255.250`` (node1) and ``172.16.255.251`` (node2).
These two IP addresses will be used throughout the tutorial and configuration files.

.. warning::
   
   If these addresses conflict with your local network configuration, you will need to edit the ``Vagrantfile`` to change the IP addresses.
   You will then need to generate a new set of certificates and keys using the Flocker CLI ``flocker-ca`` tool and copy these to the virtual machines.
   This will also require you to start the node services manually.
   Therefore if your IP addresses conflict with the tutorial, please see the full :ref:`installation instructions <installing-flocker>` for more information.

.. XXX This warning needs to be reviewed, as the link is vague. See FLOC 2661

.. warning::

   On some versions of Vagrant and VirtualBox, restarting the tutorial virtual machines via the ``vagrant halt`` and ``vagrant up`` commands can result in losing the static IP configuration, making the nodes unreachable on the assigned ``172.15.255.25x`` addresses.
   In this case you should destroy and recreate the machines with the ``vagrant destroy`` and ``vagrant up`` commands.

.. note:: The two virtual machines are each assigned a 10GB virtual disk.
          The underlying disk files grow to about 5GB.
          So you will need at least 10GB of free disk space on your workstation.

#. Create a tutorial directory:

   .. code-block:: console

      alice@mercury:~/$ mkdir flocker-tutorial
      alice@mercury:~/$ cd flocker-tutorial
      alice@mercury:~/flocker-tutorial$

#. Download the Vagrant configuration file by right clicking on the link below.
   Save it in the *flocker-tutorial* directory and preserve its filename.

   .. This download is also used in the getting started guide. You will need to adjust
      it if this download is changed.

   :version-download:`Vagrantfile.template`

   .. version-literalinclude:: Vagrantfile.template
      :language: ruby
      :lines: 1-8
      :append: ...

#. Download the cluster and user credentials by right clicking on the links below.
   Save these to the *flocker-tutorial* directory too, also preserving the file names.

   .. These downloads are also used in the getting started guide. You will need to adjust
      it if these downloads are changed.
   
   :download:`cluster.crt`
   
   :download:`user.crt`
   
   :download:`user.key`

   .. code-block:: console

      alice@mercury:~/flocker-tutorial$ ls
      cluster.crt user.crt user.key Vagrantfile
      alice@mercury:~/flocker-tutorial$

#. Use ``vagrant up`` to start and provision the VMs:

   .. code-block:: console

      alice@mercury:~/flocker-tutorial$ vagrant up
      Bringing machine 'node1' up with 'virtualbox' provider...
      ==> node1: Importing base box 'clusterhq/flocker-dev'...
      ... lots of output ...
      ==> node2: ln -s '/usr/lib/systemd/system/docker.service' '/etc/systemd/system/multi-user.target.wants/docker.service'
      alice@mercury:~/flocker-tutorial$

   This step may take several minutes or more as it downloads the Vagrant image, boots up two nodes and downloads the Docker image necessary to run the tutorial.
   Your network connectivity and CPU speed will affect how long this takes.
   Fortunately this extra work is only necessary the first time you bring up a node (until you destroy it).

#. After ``vagrant up`` completes you may want to verify that the two VMs are really running and accepting SSH connections:

   .. code-block:: console

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

#. If all goes well, the next step is to configure your SSH agent.
   This will allow Flocker to authenticate itself to the VM:

   If you're not sure whether you already have an SSH agent running, ``ssh-add`` can tell you.
   If you don't, you'll see an error:

   .. code-block:: console

      alice@mercury:~/flocker-tutorial$ ssh-add
      Could not open a connection to your authentication agent.
      alice@mercury:~/flocker-tutorial$

   If you do, you'll see no output:

   .. code-block:: console

      alice@mercury:~/flocker-tutorial$ ssh-add
      alice@mercury:~/flocker-tutorial$

   If you don't have an SSH agent running, start one:

   .. code-block:: console

      alice@mercury:~/flocker-tutorial$ eval $(ssh-agent)
      Agent pid 27233
      alice@mercury:~/flocker-tutorial$

#. Finally, add the Vagrant key to your agent:

   .. code-block:: console

      alice@mercury:~/flocker-tutorial$ ssh-add ~/.vagrant.d/insecure_private_key
      alice@mercury:~/flocker-tutorial$

You now have two VMs running and easy SSH access to them.
This completes the Vagrant-related setup.


.. _upgrading-vagrant-environment:

Upgrading the Vagrant Environment
=================================

The ``Vagrantfile`` used in this tutorial installs an RPM package called ``clusterhq-flocker-node`` on both the nodes.
If you already have a tutorial environment from a previous release, you'll need to ensure that both tutorial nodes are running the latest version of ``clusterhq-flocker-node`` before continuing with the following tutorials.

First check the current Flocker version on the nodes.
You can do this by logging into each node and running the ``flocker-dataset-agent`` command with a ``--version`` argument.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh root@172.16.255.250 flocker-dataset-agent --version

Only proceed if you find that you are running an older version of Flocker than |version|.

If you find that you *are* running an older version, you now need to rebuild the tutorial environment.

This will ensure that you have the latest Flocker version and that you are using a pristine tutorial environment.

.. warning:: This will completely remove the existing nodes and their data.

If you have the original ``Vagrantfile``, change to its parent directory and run ``vagrant destroy``.

.. code-block:: console

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

Next delete the cached SSH host keys for the virtual machines as they will change when new VMs are created.
Failing to do so will cause SSH to think there is a security problem when you connect to the recreated VMs.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ ssh-keygen -f "$HOME/.ssh/known_hosts" -R 172.16.255.250
   alice@mercury:~/flocker-tutorial$ ssh-keygen -f "$HOME/.ssh/known_hosts" -R 172.16.255.251

Delete the original ``Vagrantfile`` and then download the latest ``Vagrantfile`` along with the cluster and user certificate and key files below and run ``vagrant up``.

   :download:`cluster.crt`
   
   :download:`user.crt`
   
   :download:`user.key`

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ vagrant up
   Bringing machine 'node1' up with 'virtualbox' provider...
   Bringing machine 'node2' up with 'virtualbox' provider...
   alice@mercury:~/flocker-tutorial$

Alternatively, if you do not have the original ``Vagrantfile`` or if the ``vagrant destroy`` command fails, you can remove the existing nodes `directly from VirtualBox`_.
The two virtual machines will have names like ``flocker-tutorial_node1_1410450919851_28614`` and ``flocker-tutorial_node2_1410451102837_79031``.

.. _`Homebrew`: http://brew.sh/
.. _`Vagrant`: https://docs.vagrantup.com/v2/
.. _`VirtualBox`: https://www.virtualbox.org/
.. _`MongoDB installation guide`: http://docs.mongodb.org/manual/installation/
.. _`directly from VirtualBox`: https://www.virtualbox.org/manual/ch01.html#idp55629568
