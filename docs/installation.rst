==================
Installing Flocker
==================

Flocker has two components that need installing:

1. The ``flocker-node`` package that runs on each node in the cluster.
   For now we recommend running the cluster using a pre-packaged Vagrant setup;
   see :doc:`tutorial/vagrant-setup`.
2. The ``flocker-cli`` package which provides command line tools to control the cluster.
   This should be installed on a machine with SSH credentials to control the cluster nodes, e.g. the
   host machine which is running the above pre-packaged Vagrant box. See below;

``flocker-cli`` Installation
============================

The Flocker CLI tool is installed using Pip_, which is available on most operating systems,
including; Windows, OSX and Linux.

(Once 'flocker-cli' is available on the Pip package index) All you need to do to install is;
``pip install flocker-cli``.

(Until then) You can also install the bleeding edge client from the current Github repo using
Virtualenv_. On a \*nix-based system you can do the following;

.. code-block:: console

   alice@mercury:~$ git clone git@github.com:ClusterHQ/flocker.git
   alice@mercury:~$ cd flocker
   alice@mercury:~/flocker$ virtualenv env
   alice@mercury:~/flocker$ python setup.py install .[doc,dev]
   alice@mercury:~/flocker$ sudo ln -s $(pwd)/contrib/flocker-deploy-dev.sh /usr/local/bin/fl-dev
   alice@mercury:~/flocker$ cd ~
   alice@mercury:~$ fl-dev --version
   0.1.0


.. _Pip: http://pip.readthedocs.org/en/latest/installing.html
.. _Virtualenv: http://virtualenv.readthedocs.org/en/latest/virtualenv.html
