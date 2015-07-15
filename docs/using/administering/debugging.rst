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

Ubuntu Bug Reporting
^^^^^^^^^^^^^^^^^^^^

When reporting issues with Flocker on Ubuntu always include copies of all the log files.

The relevant logs can be exported by running the following commands as root:

.. prompt:: bash [root@node1]# auto

   SUFFIX="${HOSTNAME}_$(date +%s)"
   ARCHIVE_NAME="clusterhq_flocker_logs_${SUFFIX}"
   # Export all logs into a single directory
   mkdir "${ARCHIVE_NAME}"
   # Export the raw Eliot log messages from all enabled Flocker services
   find /var/log/flocker -type f \
   | xargs --max-args=1 --replace='{}' -- basename {} '.log'  \
   | while read filename; do
       gzip < "/var/log/flocker/${filename}.log" > "${ARCHIVE_NAME}/${filename}-${SUFFIX}.log.gz"
   done
   # Export the full syslog since last boot with UTC timestamps
   gzip < /var/log/syslog > "${ARCHIVE_NAME}/all-${SUFFIX}.log.gz"
   # Create a single archive file
   tar --create --file "${ARCHIVE_NAME}.tar" "${ARCHIVE_NAME}"
   rm -rf "${ARCHIVE_NAME}"


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

When reporting issues with Flocker on Centos 7 always include copies of all the log files.

The relevant logs can be exported by running the following commands as root:

.. prompt:: bash [root@node1]# auto

   SUFFIX="${HOSTNAME}_$(date +%s)"
   ARCHIVE_NAME="clusterhq_flocker_logs_${SUFFIX}"
   # Export all logs into a single directory
   mkdir "${ARCHIVE_NAME}"
   # Export the raw Eliot log messages from all enabled Flocker services
   systemctl  list-unit-files --no-legend \
   | awk '$1~/^flocker-\S+\.service$/ && $2=="enabled" {print $1}' \
   | while read unitname; do
       journalctl --all --output=cat --unit="${unitname}" | gzip > "${ARCHIVE_NAME}/${unitname}-${SUFFIX}.log.gz"
   done
   # Export the full journal since last boot with UTC timestamps
   journalctl --all --boot | gzip > "${ARCHIVE_NAME}/all-${SUFFIX}.log.gz"
   # Create a single archive file
   tar --create --file "${ARCHIVE_NAME}.tar" "${ARCHIVE_NAME}"
   rm -rf "${ARCHIVE_NAME}"




.. _`systemd's journal`: http://www.freedesktop.org/software/systemd/man/journalctl.html
.. _`eliot`: https://github.com/ClusterHQ/eliot
.. _`eliottree`: https://github.com/jonathanj/eliottree
