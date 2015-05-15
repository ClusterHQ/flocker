=========
Debugging
=========

Logging
-------

Flocker processes generally use `eliot`_ for logging.
These logs can be rendered as an ASCII tree using `eliottree`_.

Logs from the Docker containers can be viewed using `the Docker CLI <https://docs.docker.com/reference/commandline/cli/#logs>`_.

Ubuntu
^^^^^^

XXX This should be documented, see :issue:`1877`.

Fedora / CentOS
^^^^^^^^^^^^^^^

Logs from the Flocker processes running on the nodes are written to `systemd's journal`_.
They have unit names starting constructed with a ``flocker-`` prefix, e.g. ``flocker-agent``.

It is possible to see the available unit names, and then view the logs with ``journalctl``:

.. prompt:: bash $

   $ ls /etc/systemd/system/multi-user.target.wants/flocker-*.service | xargs -n1 basename
   flocker-agent.service
   flocker-container-agent.service
   flocker-control.service
   $ journalctl -u flocker-agent
   $ journalctl -u flocker-container-agent
   $ journalctl -u flocker-control

.. _`systemd's journal`: http://www.freedesktop.org/software/systemd/man/journalctl.html
.. _`eliot`: https://github.com/ClusterHQ/eliot
.. _`eliottree`: https://github.com/jonathanj/eliottree
