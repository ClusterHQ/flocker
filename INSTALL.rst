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

   mkdir -p /opt/flocker
   truncate --size 1G /opt/flocker/pool-vdev
   zpool create flocker /opt/flocker/pool-vdev

Client
------

Fedora
^^^^^^

::

   yum localinstall http://archive.clusterhq.com/fedora/flocker-release$(rpm -E %dist).noarch.rpm
   yum install flocker-cli

::
   flocker-deploy <...>


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
