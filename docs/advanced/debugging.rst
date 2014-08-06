=========
Debugging
=========

Logging
=======

The Flocker processes running on the nodes will write their logs to ``/var/log/flocker/``.
The log files are named ``<processname>-<pid>.log``, e.g. ``flocker-volume-1234.log``.

Logs from the Docker containers are written to `systemd's journal`_ with a unit name constructed with a ``ctr-`` prefix.
For example if you've started an application called ``mymongodb`` you can view its logs by running the following command on the node where the application was started:

.. code-block:: console

   $ journalctl -u ctr-mymongodb

.. _`systemd's journal`: http://www.freedesktop.org/software/systemd/man/journalctl.html
