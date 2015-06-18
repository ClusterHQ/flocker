.. _upgrading-flocker:

=========
Upgrading
=========

A Flocker cluster can be upgraded to a newer version of Flocker while preserving all data and configuration of the Flocker cluster provided certain steps are followed.
The correct steps to follow may vary depending on the versions of Flocker being upgraded from and to.
A common requirement for all currently supported upgrade paths is that all nodes and the control service must be running the same version of Flocker.

Flocker 1.0.1
-------------

Recommended Steps
^^^^^^^^^^^^^^^^^

  #. Stop the control service and the agent services on all nodes.
  #. Install Flocker 1.0.1 on all hosts in the Flocker cluster.
  #. Reboot each of the agent nodes.
  #. If you have not configured the Flocker agents to start automatically on boot,
     restart the agent services on all nodes.
  #. Restart the control service.

Details
^^^^^^^

The upgrade to Flocker 1.0.1 involves changing the metadata on the filesystems created on the volumes managed by the AWS EBS and OpenStack Cinder storage drivers.
These metadata changes will be made automatically by ``flocker-dataset-agent`` as part of its normal operation.
However, these metadata changes can only be performed when the filesystems themselves are unmounted (therefore not in use).
The easiest way to ensure ``flocker-dataset-agent`` will be able to perform these upgrades is to reboot the node where the agent is running.
When the node starts up again, all Flocker-managed filesystems will start unmounted.
``flocker-dataset-agent`` will upgrade each filesystem before re-mounting the filesystem for use by applications.
You can observe the upgrade process by finding ``agent:blockdevice:1.0.0:upgrade:fs`` and ``agent:blockdevice:1.0.0:mounted:fs`` events in the ``flocker-dataset-agent`` log.
The former indicates a filesystem upgrade is being attempted.
The latter indicates a filesystem was found mounted and no upgrade was attempted.

Flocker 1.0.0
-------------

There are no supported upgrade paths from versions of Flocker older than 1.0.0.
