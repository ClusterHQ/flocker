Instalation Instructions
========================

Server
------

The only supported node system is fedora 20.

Fedora
^^^^^^

::

   yum localinstall http://archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm
   yum localinstall http://archive.clusterhq.com/fedora/flocker-release$(rpm -E %dist).noarch.rpm
   yum install flocker-node

Create a zfs pool. The following create a pool as a file in ``/``::

   truncate -s 2G /flocker-pool
   zpool create flocker /flocker-pool

Client
------

Fedora
------

::

   yum localinstall http://archive.clusterhq.com/fedora/flocker-release$(rpm -E %dist).noarch.rpm
   yum install flocker-cli

::
   flocker-deploy <...>


Ubuntu
^^^^^^

::

   sudo apt-get install python-virtualenv
   virtualenv ~/flocker
   ~/flocker/bin/pip install flocker

::

   ~/flocker/bin/flocker-deploy <...>


OS X
^^^^

::

   wget(?) https://glyph.im/pip/bootstrap.sh
   ./bootstrap.sh
   mkvirtualenv flocker
   pip install flocker

::
   workon flocker
   flocker-deploy <...>
