.. _leases:

==============
Flocker Leases
==============

Leases prevent multiple applications from requesting the same dataset on different nodes at the same time.

Requesting Leases
=================

Leases are accessed via the :ref:`api` exposed by the Flocker control service, however most users will interact with leases through the :ref:`docker-plugin`, which will handle requesting leases for you.

Acquiring and Releasing Leases
==============================

After a dataset has been moved to a node, an application can acquire a lease for that dataset.
While the lease is active, any other requests for that dataset on a different node will be rejected with an error.
When an application no longer requires a dataset it can **release** the lease.

Leases can be released by any user of the API, so if an application does not release a lease, it can be released manually.

Lease Expiration
================

Leases can be configured to expire after a given time.
Before that time has passed, a lease can be refreshed with a new expiration time.
