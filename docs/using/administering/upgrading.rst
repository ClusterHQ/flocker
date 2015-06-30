.. _upgrading:

=========
Upgrading
=========

A Flocker cluster can be upgraded to a newer version of Flocker while preserving all data and configuration of the Flocker cluster provided certain steps are followed.
The correct steps to follow may vary depending on the versions of Flocker being upgraded from and to.

.. note:: A common requirement for all currently supported upgrade paths is that all nodes and the control service must be running the same version of Flocker.

Flocker v1.0.2
--------------

Recommended Steps
^^^^^^^^^^^^^^^^^

#. Stop the agent services on all nodes, and then stop control service.
#. Install Flocker v1.0.2 on all nodes in the Flocker cluster.
#. If you are running on CentOS, run ``systemctl restart rsyslog`` on all machines running Flocker services.
#. Restart the Docker service.
#. Restart the control service.
#. Restart the agent services on all nodes.

Note that once you have done this applications you have previously configured to always restart will not be restarted.
You will need to remove and re-add them every time they exit or you reboot.
This feature was broken in previous releases and so has been temporarily disabled in this release.

Flocker v1.0.1
--------------

Recommended Steps
^^^^^^^^^^^^^^^^^

#. Stop the agent services on all nodes, and then stop control service.
#. Install Flocker v1.0.1 on all nodes in the Flocker cluster.
#. Restart the control service.
#. If you are using the EBS storage backend, reboot each of the agent nodes.
#. If you have not configured the Flocker agents to start automatically on boot,
   restart the agent services on all nodes.

Details
^^^^^^^

The upgrade to Flocker v1.0.1 involves changing the way the EBS storage backend maps volumes to devices: in version 1.0.0, there were occasional errors in this mapping.
As a result, some devices may have been mounted in the wrong location.
The easiest way to fix this problem is to restart the agent nodes with Flocker v1.0.1 installed.

Other storage backends do not require a restart as they were unaffected by this bug.

Flocker v1.0.0
--------------

There are no supported upgrade paths from versions of Flocker older than v1.0.0.
