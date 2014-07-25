==================
Installing Flocker
==================

Flocker has two components that need installing:

1. The ``flocker-node`` package that runs on each node in the cluster.
   For now we recommend running the cluster using a pre-packaged Vagrant setup; see :doc:`tutorial/vagrant-setup`.
2. The ``flocker-cli`` package which provides command line tools to controls the cluster.
   This should be installed on a machine with SSH credentials to control the cluster nodes, e.g. the machine which is running Vagrant.


Ubuntu
======

To install ``flocker-cli`` on Ubuntu you can run the following script:

:download:`ubuntu-install.sh`

.. literalinclude:: ubuntu-install.sh
   :language: sh

Save the script to a file, and then run it:

.. code-block:: console

   alice@mercury:~$ sh ubuntu-install.sh

The ``flocker-deploy`` command line program will now be available in ``flocker-tutorial/bin/``:

.. code-block:: console

   alice@mercury:~$ cd flocker-tutorial
   alice@mercury:~/flocker-tutorial$ bin/flocker-deploy --version
   0.1.0
   alice@mercury:~/flocker-tutorial$ export PATH="${PATH:+${PATH}:}${PWD}/bin"
   alice@mercury:~/flocker-tutorial$ flocker-deploy --version
   0.1.0
