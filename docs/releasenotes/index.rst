=============
Release Notes
=============

See the :ref:`upgrading instructions <upgrading>` for information on upgrading Flocker clusters from earlier releases.

You can learn more about where we might be going with future releases by:

* Stopping by the ``#clusterhq`` channel on ``irc.freenode.net``.
* Visiting our GitHub repository at https://github.com/ClusterHQ/flocker.


This Release
============

v1.13.0
-------

* ``flocker-deploy`` command line utility is now deprecated.

Previous Releases
=================

.. contents::
   :local:
   :backlinks: none
   :depth: 2

v1.12.0
-------

* The OpenStack Cinder backend for Flocker will now use the Cinder version 2 API if it is available. 
  This allows Flocker to work in OpenStack clusters where there are more than 1000 Cinder volumes.
* Flocker can now be :ref:`installed on Redhat Enterprise Linux 7 <rhel-7-install-standalone-flocker>`.
* The Flocker control service and dataset agents now use less CPU and network bandwidth whilst converging on configuration changes.
* The Flocker dataset agent will now reconnect to the control service within 30 seconds, even after an extended disconnection.
* The Flocker documentation search engine is now faster and generates more relevant results.

v1.11.0
-------

* The dataset agent now has backend support for :ref:`Google Compute Engine <gce-dataset-backend>`.
* Flocker is now significantly more efficient.
  The control and agent services use far less CPU time when idle and far less CPU time when converging on a configuration change.
  This allows larger clusters containing more datasets and supporting more frequent configuration changes.
* The container agent is now optional and can be safely disabled if you don't expect to be using Flocker's deprecated container API or ``flocker-deploy``.
  The :ref:`Flocker plugin for Docker<plugin>` allows you to use Flocker from Docker without using Flocker's container API.
* The dataset agent now has backend support for :ref:`Open vStorage <open-vstorage-backend>`.
* A race condition where multiple volumes for a given dataset could be created and used has been fixed.
  This could lead to the appearance of data loss, as different volumes get used.
  Now, even if multiple volumes are created, only a single volume will be used.
  This was particularly likely to occur on AWS.
* The Flocker client tools can once again be installed on OS X 10.10.
  A regression in the Flocker Homebrew tap file has been fixed.

v1.10.2
-------

* Decreased the CPU usage of the Control Service API under load.
   * The Control Service API enforces that a dataset's ``maximum_size`` is an integer, rather then any number.
   * The Control Service API no longer validates its responses at runtime.
* Block device plugins can now specify the configuration keys they require.
  This allows better error messages to be generated.
* Several outdated references in the documentation have been removed.

v1.10.1
-------

* The :ref:`Flocker documentation <supported-orchestration-frameworks>` has been re-designed to better reflect that Flocker now integrates with Cluster Managers, rather than providing its own container management features.
* The new :ref:`CloudFormation installer <cloudformation>` has been made available, to provide a far simpler installation experience for users on AWS.
* The :ref:`Flocker plugin for Docker <plugin>` should support the direct volume listing and inspection functionality added to Docker 1.10.
* Fixed a regression that caused block device agents to poll backend APIs like EBS too frequently in some circumstances.
* Increase limit on maximum Flocker volumes per AWS instance from 11 to 21.

v1.10.0
-------

Unreleased.

v1.9.0
------

* Tested against Docker version 1.9.1.
* The REST API now supports :ref:`conditional requests<conditional requests>` of the form "only create this dataset if the configuration hasn't changed since I last checked it", allowing for e.g. enforcement of metadata uniqueness.
* Fixed a bug where :ref:`Flocker plugin for Docker<plugin>` could not create a dataset that had the same name as a previously deleted dataset.
* Now supporting Ubuntu 15.10 instead of Ubuntu 15.04 for the Flocker client.
* Added documentation for the :ref:`EMC VMAX <emc-dataset-backend>` driver.
* Region and zone configuration for AWS is now validated before use.
* Flocker now reports an error when busy EBS volumes cannot be detached.
* Fixed a bug where Flocker would attempt to attach EBS volumes to device paths that are assigned to volumes attached outside of Flocker.
* Flocker now supports all valid Docker container names.
* The container API client now allows volumes to be attached to containers.
* The container API client now supports retrieval of container state.
* Fixed a bug where the Flocker control service sometimes listened on the wrong port.
* The :ref:`Flocker plugin for Docker<plugin>` now supports specifying the size during volume creation.
* Fixed a bug where Flocker would fail to service requests that had an unexpected format.


v1.8.0
------

* The :ref:`Flocker plugin for Docker<plugin>` is now able to use datasets created directly via Flocker so long as the metadata has a matching ``"name"`` value.
* Better error reporting for the Flocker plugin for Docker.
* Added a new REST API for :http:get:`looking up node identity by era</v1/state/nodes/by_era/(era)>`; eras are reset after every reboot.
  This allows robust interaction with Flocker across reboots without getting stale data.
  As a result we were able to remove a delay in startup time that was a temporary workaround for the issue.
* Fixed a bug where datasets that hadn't had a filesystem created on them could never be mounted;
  existing flocker datasets without filesystems now have a filesystem created on them.

v1.7.2
------

* Moved the installation instructions for the Flocker plugin for Docker, to prevent issues when installing and configuring the plugin.
* Added documentation for :ref:`Dell SC Series <dell-dataset-backend>`, :ref:`Huawei <huawei-backend>` and :ref:`NexentaEdge <nexenta-backend>` drivers.

v1.7.1
------

* Prevent disconnect/reconnect cycles causing high CPU load.

v1.7.0
------

* Added support for :ref:`storage profiles<storage-profiles>`.

v1.6.1
------

* Updated the Vagrant tutorial box to work with Docker 1.9.

v1.6.0
------

* The :ref:`Flocker plugin for Docker<plugin>` is now compatible with Docker 1.9.
* New EBS and OpenStack Cinder volumes created by Flocker will now have ``flocker-<dataset ID>`` as their name, to make it easier to find them in their respective cloud administration UIs.
  Existing volumes created by older versions of Flocker will continue to have no name.

v1.5.0
------

* The :ref:`Flocker plugin for Docker<plugin>` is now part of the core Flocker system, instead of an experimental Labs project.
* Unexpected errors in agent state discovery no longer break the agent convergence loop.
* journald logs are now easier to filter and read.
  See the :ref:`documentation <flocker-logging>` for more information.
* The control service uses much less CPU, allowing for larger clusters.
* Flocker CLI now installs on OS X 10.11.

v1.4.0
------

* The :ref:`dataset API <api>` added support for :ref:`leases <leases>`.
  Leases prevent a dataset from being deleted or moved off a node.
* Fix line splitting when logging to `systemd`'s journal.
* Various performance and scalability improvements.
* Remove limits on size of configuration and state in agent protocol.
* Prevent repeated restart of containers with CPU shares or memory limits.

v1.3.1
------

* Fixed a bug in previous fix where OpenStack Cinder volumes failed to mount.
* Creation of a ZFS pool using ZFS 0.6.5 or later requires the setting of a ``ZFS_MODULE_LOADING`` environment variable.

v1.3
----

* Fixed a bug where OpenStack Cinder volumes could be mapped to the wrong device and therefore mounted in the wrong location.

v1.2
----

* If you upgrade to Docker 1.8.1 you may find pulling images unreliable in flocker-deploy and the Flocker Containers API due to Docker bug `#15699`_.
  You may be able to workaround this by appending the image tag to the end of the image name (e.g. :latest).
* Flocker ``.deb`` and ``.rpm`` packages no longer declare any dependency on a Docker package.
  Docker is required for the container management functionality but a Docker package must be selected and installed manually.
  This provides more control over the version of Docker used with Flocker.
* Flocker's container management functionality now integrates with SELinux.
  Flocker can now be used in ``SELinux=enforcing`` environments.
* Flocker now includes :ref:`bug reporting documentation<flocker-bug-reporting>` and an accompanying command line tool called ``flocker-diagnostics``.

v1.1
----

* ``flocker-deploy`` supports specification of the pathnames of certificate and key files.
* The agent configuration file allows specification of a CA certificate for OpenStack HTTPS verification.
  See :ref:`openstack-dataset-backend`.
* Flocker can now start containers using images from private Docker registries.
* On CentOS 7, installing or upgrading the ``clusterhq-flocker-node`` package now reloads the ``rsyslog`` service to ensure that Flocker logging policy takes immediate effect.

v1.0.3
------

* On Ubuntu-14.04, log files are now written to /var/log/flocker and rotated in five 100MiB files, so as not fill up the system disk.

v1.0.2
------

* On CentOS 7, Flocker logs are no longer written to /var/log/messages since this filled up disk space too quickly.
  The logs are still available via journald.
* The "on-failure" and "always" restart policies for containers have been temporarily disabled due to poor interaction with node reboots for containers with volumes (FLOC-2467).

v1.0.1
------

Upgrading is strongly recommended for all users of v1.0.0.

* The EBS storage driver now more reliably selects the correct OS device file corresponding to an EBS volume being used.
* Additional safety checks were added to ensure only empty volumes are formatted.
* ClusterHQ Labs projects, including the Flocker Docker Plugin and an experimental Volumes CLI and GUI are now documented.

v1.0
----

* Dataset backend support for :ref:`AWS Elastic Block Storage (EBS)<aws-dataset-backend>`, :ref:`OpenStack Cinder<openstack-dataset-backend>`, and :ref:`EMC ScaleIO and XtremIO<emc-dataset-backend>`.
* Third parties can write Flocker storage drivers so that their storage systems work with Flocker.
  See :ref:`contribute-flocker-driver`.
* It is now necessary to specify a dataset backend for each agent node.
* Flocker-initiated communication is secured with TLS.
* ``flocker-deploy`` now requires the hostname of the control service as its first argument.
* Added REST API functions to manage containers in a cluster alongside datasets.
  See :ref:`api`.
* Removed support for installing ``flocker-node`` on Fedora 20.
* Ubuntu CLI installation instructions now use Debian packages instead of pip packaging.
* Bug fixes and improvements focused on security and stability across platforms.

v0.4
----

* New :ref:`REST API<api>` for managing datasets.
* Applications can now be configured with a restart configuration.
* Volumes can now be configured with a maximum size.
* Documentation now includes instructions for installing flocker-node on CentOS 7.
* SELinux must be disabled before installing Flocker.
  A future version of Flocker may provide a different integration strategy.

v0.3.2
------

* Documented how to configure the Fedora firewall on certain cloud platforms.


v0.3.1
------

* Applications can now be configured with a CPU and memory limit.
* Documentation now includes instructions for installing flocker-node on Fedora 20.
* Documentation now includes instructions for deploying ``flocker-node`` on three popular cloud services: Amazon EC2, Rackspace, and DigitalOcean.


v0.3
----

* ``geard`` is no longer used to manage Docker containers.
* Added support for `Fig`_ compatible application configuration files.


v0.2
----

* Moving volumes between nodes is now done with a two-phase push that should dramatically decrease application downtime when moving large amounts of data.
* Added support for environment variables in the application configuration.
* Added basic support for links between containers in the application configuration.

v0.1
----

Everything is new since this is our first release.


.. _`Fig`: http://www.fig.sh/yml.html
.. _`#15699`: https://github.com/docker/docker/issues/15699
