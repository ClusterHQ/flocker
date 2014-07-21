==================
Installing Flocker
==================

Flocker has two components that need installing:

1. The software that runs on each node in the cluster.
   For now we recommend running the cluster using a pre-packaged Vagrant setup; see `tutorial/vagrant-setup`.
2. The ``flocker-cli`` package which provides command line tools to controls the cluster.
   This should be installed on a machine with SSH credentials to control the cluster nodes, e.g. the machine which is running Vagrant.


Ubuntu 14.04
============

To install ``flocker-cli`` on Ubuntu 14.04 you can run the following script:

:download:`ubuntu-install.sh`

.. literalinclude:: ubuntu-install.sh
   :language: shell
