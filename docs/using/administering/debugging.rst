.. _debugging-flocker:

=========
Debugging
=========

.. _flocker-logging:

Logging
-------

Flocker processes use `eliot`_ for logging.
These logs can be rendered as an ASCII tree using `eliottree`_.

Logs from the Docker containers can be viewed using `the Docker CLI <https://docs.docker.com/reference/commandline/cli/#logs>`_.

Ubuntu
^^^^^^

XXX This should be documented, see :issue:`1877`.

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

.. _flocker-bug-reporting:

Bug Reporting
-------------

When reporting issues with Flocker please include:

* The version of Flocker you are using.
* Your operating system and version.
* Your Linux kernel version.
* The version of Docker you are using, and Docker configuration details.
* Your node IP addresses.
* Your node hostname.
* Disk and partition configuration details.
* All recent syslog content.
* Any separate Flocker service log files.

.. warning:: The exported log files may contain sensitive information.

Export Logs Using ``flocker-diagnostics``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``flocker-diagnostics`` command can be used to gather this information on Ubuntu 14.04 and CentOS 7.

.. prompt:: bash #

   flocker-diagnostics

``flocker-diagnostics`` will create a ``tar`` archive in the current directory.
It will print the full path of the archive before it exits.

Exporting Logs Manually
^^^^^^^^^^^^^^^^^^^^^^^

Alternatively, the information can be gathered manually using the following commands:

* Flocker version:

  .. prompt:: bash #

     flocker-control --version

* Operating system and version:

  .. prompt:: bash #

     cat /etc/os-release

* Linux kernel version:

  .. prompt:: bash #

     uname -a

* Docker version and configuration:

  .. prompt:: bash #

     docker version
     docker info

* IP Addresses:

  .. prompt:: bash #

     ip addr

* Hostname:

  .. prompt:: bash #

     hostname

* Disk and partition configuration details:

  .. prompt:: bash #

     fdisk -l
     lsblk --all

* Flocker log files (see :ref:`Flocker logging <flocker-logging>` above)

Profiling
---------

.. warning::

   It is not recommended to use profiling while relying on Flocker within a production environment as there is a performance overhead.

Control Service
^^^^^^^^^^^^^^^

It is possible to obtain :py:mod:`cProfile` profiling data of the :ref:`Control Service <control-service>` between two user defined intervals.

Profiling is disabled by default.
To enable profiling of the Control Service run the following command as root on the control node:

.. prompt:: bash #

   pkill -SIGUSR1 flocker-control

Profiling data will then be collected until a signal to stop profiling is received.

To stop profiling run the following command as root on the control node:

.. prompt:: bash #

   pkill -SIGUSR2 flocker-control

This will also output the profiling data to a file named :file:`/var/lib/flocker/profile-<TIMESTAMP>`.
This file will include all profiling data collected up to that point, including from previous intervals of profiling.

See :py:mod:`pstats` for details on how to extract information from this file.
For example:

.. code-block:: python

   import pstats

   profile = pstats.Stats('profile-20150917161214')
   profile.sort_stats('cumulative').print_stats(10)


.. _`systemd's journal`: http://www.freedesktop.org/software/systemd/man/journalctl.html
.. _`eliot`: https://github.com/ClusterHQ/eliot
.. _`eliottree`: https://github.com/jonathanj/eliottree
