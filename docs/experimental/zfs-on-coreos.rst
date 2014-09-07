=============
ZFS on CoreOS
=============

This tutorial will show you how to get ZFS running on CoreOS, and then demos ZFS ``send`` and ``receive`` to move a volume from one node to another.

This is a just one of the prerequisites to getting Flocker_ working on CoreOS_, in order to be able to move stateful services in containers between nodes.

.. warning::

    This is a highly experimental proof-of-concept and should not be used for anything resembling production use cases.

The following instructions have been tested against CoreOS 423.0.0 (alpha) and CoreOS 367.1.0 (stable) and may or may not work against different versions.

Get a CoreOS cluster
====================

If you have not already, procure two or more CoreOS machines.

For this tutorial, we are using CoreOS on Vagrant_ on OSX::

    git clone https://github.com/coreos/coreos-vagrant.git
    cd coreos-vagrant
    cp config.rb.sample config.rb
    vagrant up --provider=virtualbox

Now perform the remainder of the installation instructions on all of your nodes.

Download our ZFS environment
============================

Perform the following on each node to load the experimental ZFS kernel modules::

    # SSH to the node
    vagrant ssh core-01
    # Download our bits
    wget http://storage.googleapis.com/experiments-clusterhq/zfs-coreos/coreos-gentoo-prefix-wip.tar.lz4.xz
    wget http://storage.googleapis.com/experiments-clusterhq/zfs-coreos/liblz4.so.0.0
    wget http://storage.googleapis.com/experiments-clusterhq/zfs-coreos/lz4c
    chmod +x lz4c
    chmod +x liblz4.so.0.0
    # Extract the tarball
    xzcat coreos-gentoo-prefix-wip.tar.lz4.xz | env LD_LIBRARY_PATH=. ./lz4c -d | tar x
    # Enter Gentoo Prefix Shell
    gentoo/startprefix
    # Load modules
    sudo modprobe -v -d $HOME/gentoo zfs
    # Setup aliases
    alias zpool='sudo $(which zpool)'
    alias zfs='sudo $(which zfs)'

Now you should be able to test that basic ZFS commands work::

    core@core-01 ~ $ zpool status
    no pools available

Great!
We now have working ZFS support on this system, but no ZFS pools yet.

Create a ZFS pool
=================

The easiest way to do this is to create a ZFS pool in a file::

    mkdir -p /opt/flocker
    truncate --size 1G /opt/flocker/pool-vdev
    zpool create flocker /opt/flocker/pool-vdev

(For the adventurous who wants to try running ZFS on a block device, try shutting down your VM, attaching a new disk, booting the VM, running the commands above again, skipping the first two lines and replacing ``/opt/flocker/pool-vdev`` with the block device of the new disk, e.g. ``/dev/sdb``.)

You can now inspect the state of the ZFS pool with ``zpool status``::

    core@core-01 ~ $ zpool status
      pool: hpool
     state: ONLINE
      scan: none requested
    config:

        NAME        STATE     READ WRITE CKSUM
        hpool       ONLINE       0     0     0
          sdb       ONLINE       0     0     0

    errors: No known data errors

You can now experiment with ZFS on CoreOS!


.. _Flocker: https://docs.clusterhq.com/en/0.1.0/introduction.html
.. _CoreOS: https://coreos.com/
.. _Vagrant: https://coreos.com/docs/running-coreos/platforms/vagrant/
