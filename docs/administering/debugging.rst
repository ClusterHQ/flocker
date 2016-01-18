.. _debugging-flocker:

=========
Debugging
=========

.. _flocker-logging:

Logging
=======

Flocker processes use the `Eliot`_ framework for logging.
Eliot structures logs as a tree of actions, which means given an error you can see what Flocker actions caused the errors by finding the other messages in the tree.
The tree of actions can also span processes; thus you can trace API calls from within the Docker plugin and see the effects in the Flocker control service logs.
Messages can be rendered into a human-readable tree using the `eliot-tree`_ command line tool, which is pre-installed with Flocker.
Eliot also includes a tool called ``eliot-prettyprint`` which renders messages into a more human-readable format but does not present them in a tree structure.

Logs from the Docker containers can be viewed using `the Docker CLI <https://docs.docker.com/reference/commandline/cli/#logs>`_.

To view the Flocker logs, (as described below for :ref:`ubuntu-logs` or :ref:`centos-logs`), you will need to be logged in as root.

.. _ubuntu-logs:

Ubuntu
^^^^^^

Logs from the Flocker processes running on the nodes can be found in the :file:`/var/log/flocker` directory.
They have unit names that begin with a ``flocker-`` prefix.

For example, to find all logged errors for ``flocker-dataset-agent``, run:

.. prompt:: bash [root@ubuntu]#

   cat /var/log/flocker/flocker-dataset-agent.log

.. _centos-logs:

CentOS 7
^^^^^^^^

Logs from the Flocker processes running on the nodes are written to `systemd's journal`_.
They have unit names that begin with a ``flocker-`` prefix.
For example, ``flocker-dataset-agent``.

It is possible to see the available unit names, and then view the logs with ``journalctl``:

.. prompt:: bash [root@centos]# auto

   [root@centos]# ls /etc/systemd/system/multi-user.target.wants/flocker-*.service | xargs -n 1 -I {} sh -c 'basename {} .service'
   flocker-dataset-agent
   flocker-container-agent
   flocker-control
   [root@centos]# journalctl -u flocker-dataset-agent

When outputting logs to ``eliot-prettyprint`` or ``eliot-tree`` you will want to call ``journalctl`` with additional options ``--all --output cat`` to ensure the output can be read correctly by these tools.

Using ``journalctl`` we can find all logged errors:

.. prompt:: bash [root@centos]# auto

   [root@centos]# journalctl --all --output cat -u flocker-dataset-agent --priority=err | eliot-prettyprint
   ce64eb77-bb7f-4e69-83f8-07d7cdaffaca -> /2
   2015-09-23 21:26:37.972945Z
      action_type: flocker:dataset:resize
      action_status: failed
      exception: exceptions.ZeroDivisionError
      reason: integer division or modulo by zero

The first part of the first line of each message, in this case ``ce64eb77-bb7f-4e69-83f8-07d7cdaffaca``, is an identifier shared by all actions in the particular tree (or "task") that led up to this error.
We can use it to find all messages related to this particular error in an effort to figure out what caused it; we'll output to ``eliot-tree`` so we can see the structure of messages:

.. prompt:: bash [root@centos]# auto

   [root@centos]# journalctl --all --output cat -u flocker-dataset-agent ELIOT_TASK=ce64eb77-bb7f-4e69-83f8-07d7cdaffaca | eliot-tree

We can also find all messages of a particular type.
Some useful messages types for agents include:

* ``flocker:agent:converge``: The main entry point to the convergence algorithm, which will include the latest global cluster configuration and state known to the agent.
* ``flocker:agent:send_to_control_service``: The locally discovered state that the agent will send to the control service and use to calculate the necessary changes to run locally.
* ``flocker:agent:converge:actions``: The necessary changes to local state as calculated by the agent based on configuration and state.

In the following example we find what actions the dataset agent decided it needed to run most recently:

.. prompt:: bash [root@centos]# auto

   [root@centos]# journalctl --all --output cat -u flocker-dataset-agent ELIOT_TYPE=flocker:agent:converge:actions | tail -1 | eliot-prettyprint
   32e5b4e9-0a8c-4b5c-9895-d2a88315a8d7 -> /2/4
   2015-09-02 13:42:28.943926Z
     message_type: flocker:agent:converge:actions
     calculated_actions: _InParallel(changes=pvector([CreateBlockDeviceDataset(mountpoint=FilePath('/flocker/ea7afeba-6179-4149-16c1-5724fd5c8fd7'), dataset=Dataset(deleted=False, dataset_id=u'ea7afeba-6179-4149-16c1-5724fd5c8fd7', maximum_size=80530636800, metadata=pmap({u'name': u'my-database'})))]))

We can then find the full set of actions leading up to this decision, as well as the results of the block device creation, by searching for the task UUID:

.. prompt:: bash [root@centos]# auto

   [root@centos]# journalctl --all --output cat -u flocker-dataset-agent ELIOT_TASK=32e5b4e9-0a8c-4b5c-9895-d2a88315a8d7 | eliot-tree


.. _flocker-bug-reporting:

Bug Reporting
=============

When reporting issues with Flocker please include:

* The version of Flocker you are using.
* Your operating system and version.
* Your Linux kernel version.
* The version of Docker you are using, and Docker configuration details.
* Your node IP addresses.
* Your node hostname.
* Disk and partition configuration details.
* Your node hardware specification.
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

* Node hardware specification:

  .. prompt:: bash #

     lshw -quiet -json

* Flocker log files (see :ref:`Flocker logging <flocker-logging>` above)

Profiling
=========

.. warning::

   It is not recommended to use profiling while relying on Flocker within a production environment as there is a performance overhead.

Flocker Control Service
^^^^^^^^^^^^^^^^^^^^^^^

It is possible to obtain :py:mod:`cProfile` profiling data of the :ref:`control-service` between two user defined intervals.

Profiling is disabled by default.
To enable profiling of the control service run the following command as root on the control node:

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
.. _`Eliot`: https://eliot.readthedocs.org
.. _`eliot-tree`: https://github.com/jonathanj/eliottree
