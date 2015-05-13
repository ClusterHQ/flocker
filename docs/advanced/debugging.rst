=========
Debugging
=========

Logging
=======

Flocker processes generally use `eliot`_ for logging.
These logs can be rendered as an ASCII tree using `eliottree`_.

Ubuntu
^^^^^^

XXX This should be documented, see :issue:`1877`.

Fedora / CentOS
^^^^^^^^^^^^^^^

Logs from the Flocker processes running on the nodes are written to `systemd's journal`_.
They have unit names starting constructed with a ``flocker-`` prefix, e.g. ``flocker-agent``.

Logs from the Docker containers are written to `systemd's journal`_ with a unit name constructed with a ``ctr-`` prefix.
For example if you have started an application called ``mymongodb`` you can view its logs by running the following command on the node where the application was started:

.. prompt:: bash node_1$

   journalctl -u ctr-mymongodb

.. _`systemd's journal`: http://www.freedesktop.org/software/systemd/man/journalctl.html
.. _`eliot`: https://github.com/ClusterHQ/eliot
.. _`eliottree`: https://github.com/jonathanj/eliottree

# TODO move this to a new file
Testing Code on Nodes
=====================

`Buildbot`_ is the canonical testing tool for code on a branch.
It creates nodes on Vagrant and various cloud providers and installs packages from a branch onto each node.

However, sometimes it might be useful to modify code on an existing node.

To do this, start with some nodes which are configured correctly for Flocker.
# TODO document that option
A simple way to do this is to run the :ref:`acceptance test runner <acceptance-testing>` with the ``--keep`` option.

Log in to each node in the cluster, forwarding the authentication agent connection:

.. prompt:: bash alice@mercury$

   ssh -A root@${NODE_IP}

On each node, install ``git``:

.. prompt:: bash node_1$

   # This is OS specific
   sudo yum install -y git

Clone Flocker somewhere to use later:

.. prompt:: bash node_1$

   mkdir /flocker-source
   cd /flocker-source
   git clone git@github.com:ClusterHQ/flocker.git
   cd flocker
   git checkout BRANCH-NAME

Replace the node services with the new code:

.. prompt:: bash node_1$

   rm -rf /opt/flocker/lib/python2.7/site-packages/flocker/
   cp -r /backup/flocker/flocker/ /opt/flocker/lib/python2.7/site-packages/
   systemctl restart flocker-agent flocker-control

From then on, change the files in :file:`/flocker-source/flocker` and run the above commands to replace the node services with the new code.

.. _`Buildbot`: https://build.clusterhq.com/
