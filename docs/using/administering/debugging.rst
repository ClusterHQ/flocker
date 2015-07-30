.. _debugging-flocker:

=========
Debugging
=========

Logging
-------

Flocker processes use `eliot`_ for logging.
These logs can be rendered as an ASCII tree using `eliottree`_.

Logs from the Docker containers can be viewed using `the Docker CLI <https://docs.docker.com/reference/commandline/cli/#logs>`_.

Ubuntu
^^^^^^

XXX This should be documented, see :issue:`1877`.
# FLOC-2647 Perhaps I should just close 1877 with this branch.

Ubuntu Bug Reporting
^^^^^^^^^^^^^^^^^^^^

When reporting issues with Flocker on Ubuntu please include copies of all the log files.

The relevant logs can be exported by running the following script:

:download:`flocker-log-export-ubuntu.sh`

.. literalinclude:: flocker-log-export-ubuntu.sh
   :language: sh

Save the script to a file and then run it:

.. prompt:: bash alice@mercury:~$

   sh flocker-log-export-ubuntu.sh


CentOS 7
^^^^^^^^

Logs from the Flocker processes running on the nodes are written to `systemd's journal`_.
They have unit names starting constructed with a ``flocker-`` prefix, e.g. ``flocker-dataset-agent``.

It is possible to see the available unit names, and then view the logs with ``journalctl``:

.. prompt:: bash [root@node1]# auto

   [root@node1]# ls /etc/systemd/system/multi-user.target.wants/flocker-*.service | xargs -n 1 -I {} sh -c 'basename {} .service'
   flocker-dataset-agent
   flocker-container-agent
   flocker-control
   [root@node1]# journalctl -u flocker-dataset-agent
   [root@node1]# journalctl -u flocker-container-agent
   [root@node1]# journalctl -u flocker-control


CentOS 7 Bug Reporting
^^^^^^^^^^^^^^^^^^^^^^

When reporting issues with Flocker on CentOS 7 please include copies of all the log files.

The relevant logs can be exported by running the following script:

:download:`flocker-log-export-centos.sh`

.. literalinclude:: flocker-log-export-centos.sh
   :language: sh

Save the script to a file and then run it:

.. prompt:: bash alice@mercury:~$

   sh flocker-log-export-centos.sh

.. _`systemd's journal`: http://www.freedesktop.org/software/systemd/man/journalctl.html
.. _`eliot`: https://github.com/ClusterHQ/eliot
.. _`eliottree`: https://github.com/jonathanj/eliottree
