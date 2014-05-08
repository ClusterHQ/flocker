Flocker Failover Service
------------------------

The Flocker failover service provides high-availability for the user system.
It does this with two (broadly scoped) techniques:

  1. It replicates the user filesystem to a slave host.
  2. It detects service interruption for the master host and automatically fails over to the slave host.

Host
====

During normal operation Flocker requires two hosts running the base system.
The *master* host mounts the user filesystem read-write, runs the user system, exposes itself to the Internet, etc.
It also replicates the user filesystem to the *slave* host.
The slave host accepts updates of that filesystem and otherwise stands by until an incident interferes with the master host's ability to provide service.
Then the slave host is promoted to be the master host.
It starts the user system using the most up-to-date replica of the user filesystem that it has.
If the original master host returns to service it is demoted to be the slave host and the system continues just as it was before but with the host roles reversed.
If the user filesystem has diverged on the master and slave hosts then a heuristic may be applied to select the best version to continue.
This may result in the original master regaining the master role and the original slave being demoted back to a slave.

While the original master host is compromised Flocker will allow the user system to continue operating using only one host.
However, as long as only one host is online the replication and failover features of Flocker will not be operational.

Flocker is intentionally limited to at most a two host configuration
(though a future service built on Flocker may expand this).

Configuration
=============

The failover service has a couple additional configuration requirements above and beyond those mentioned in the common document:

  * the internet addresses of the master and slave hosts
  * credentials used to allow the master and slave hosts to securely communicate with each other
