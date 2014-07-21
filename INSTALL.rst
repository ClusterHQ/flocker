Installation Instructions
=========================

Installing a Flocker node
-------------------------

Flocker nodes host containers.
The only supported node operating system is Fedora 20.

Fedora
^^^^^^

::

   yum localinstall http://archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm
   yum localinstall http://archive.clusterhq.com/fedora/flocker-release$(rpm -E %dist).noarch.rpm
   yum install flocker-node

Create a ZFS pool.
For testing purposes, you can create a pool on a loopback device on your existing filesystem::

   mkdir -p /opt/flocker
   truncate --size 1G /opt/flocker/pool-vdev
   zpool create flocker /opt/flocker/pool-vdev

Installing the Flocker client
-----------------------------

The Flocker client provides a user interface for managing a cluster of Flocker nodes.

Fedora
^^^^^^

Configure ``yum`` with the Flocker package repository and install the Flocker client package::

   yum localinstall http://archive.clusterhq.com/fedora/flocker-release$(rpm -E %dist).noarch.rpm
   yum install flocker-cli

Verify the client is installed::

   flocker-deploy --version


Ubuntu
^^^^^^

::

   sudo apt-get install virtualenvwrapper
   source /usr/share/virtualenvwrapper/virtualenvwrapper.sh
   mkvirtualenv flocker
   pip install flocker

::

   workon flocker
   flocker-deploy <...>


OS X
^^^^

::

   curl https://glyph.im/pip/bootstrap.sh
   ./bootstrap.sh
   mkvirtualenv flocker
   pip install flocker

::
   workon flocker
   flocker-deploy <...>
