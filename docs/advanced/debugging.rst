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
