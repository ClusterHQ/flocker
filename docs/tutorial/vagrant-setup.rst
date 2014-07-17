Requirements
============

To replicate the steps demonstrated in this tutorial, you will need:

  * Linux, FreeBSD, or OS X
  * `Vagrant`_ (1.6.2 or newer)
  * `VirtualBox`_
  * The OpenSSH client (the ``ssh`` and ``ssh-agent`` command-line programs)

#TODO Add a variation which works on Windows
#TODO Split dependencies into OS-specific buckets that users can focus on to figure out what *they* need
#TODO Automatically generate an archive of the downloads for this tutorial so the user doesn't have to download 50 different things

.. _`Vagrant`: https://docs.vagrantup.com/
.. _`VirtualBox`: https://www.virtualbox.org/

Setup
=====

# TODO Talk about the purpose of this setup.  Vagrant is one way to get nodes but probably not an interesting way except in the tutorial.  Auth for non-Vagrant machines will be different, eg.

Before you can deploy anything with Flocker you'll need a node onto which to deploy it.
To make this easier, this tutorial includes and assumes the use of a :download:`Vagrant configuration <Vagrantfile>` which will boot two VMs that can serve as Flocker nodes.
One important thing to note is that these VMs are statically assigned the IPs ``172.16.255.250`` (node1) and ``172.16.255.251`` (node2).
These two IP addresses will be used throughout the tutorial.

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ vagrant up node1
   Bringing machine 'node1' up with 'virtualbox' provider...
   ==> node1: Importing base box 'clusterhq/flocker-dev'...
   ... lots of output ...
   ==> node1: ln -s '/usr/lib/systemd/system/docker.service' '/etc/systemd/system/multi-user.target.wants/docker.service'
   ==> node1: ln -s '/usr/lib/systemd/system/geard.service' '/etc/systemd/system/multi-user.target.wants/geard.service'
   alice@mercury:~/flocker-tutorial$

This step may take several minutes or more.
Beyond just booting a virtual machine to use as a node for the tutorial, it will download and build the necessary ZFS kernel modules.
Your network connectivity and CPU speed will affect how long this takes.
Fortunately this extra work is only necessary the first time you bring up a node (until you destroy it).

After the ``vagrant`` command completes you may want to verify that the VM is really running and accepting SSH connections:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ vagrant status node1
   Current machine states:

   node1                     running (virtualbox)
   ...
   alice@mercury:~/flocker-tutorial$ vagrant ssh node1
   Last login: Wed Jul 16 07:51:58 2014 from 10.0.2.2
   Welcome to your Packer-built virtual machine.
   [vagrant@node1 ~]$

If all goes well, the next step is to configure your SSH agent.
This will allow Flocker to authenticate itself to the VM.
Make sure you have an SSH agent running:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ kill -0 ${SSH_AGENT_PID} && echo "ssh-agent running" || "ssh-agent not running"
   ssh-agent running
   alice@mercury:~/flocker-tutorial$

If you see ``ssh-agent not running`` as the output of this command then you need to start one:

.. code-block:: console

   alice@mercury:~/flocker-tutorial$ eval $(ssh-agent)
   Agent pid 27233
   alice@mercury:~/flocker-tutorial$

Then add the Vagrant key to your agent:

   alice@mercury:~/flocker-tutorial$ ssh-add ~/.vagrant.d/insecure_private_key
   alice@mercury:~/flocker-tutorial$

This completes the Vagrant-related setup.
