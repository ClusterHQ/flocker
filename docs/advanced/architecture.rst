============================
Flocker Cluster Architecture
============================

This document describes the Flocker cluster's architecture.
More accurately, it describes the architecture Flocker is moving towards, a transition that is still in progress.

The Flocker cluster is composed of two sets of services:

1. **The control service** that you can interact with using a :ref:`HTTP API<api>` to modify the desired configuration of the cluster.
2. **Convergence agents** in charge of modifying the cluster state to match the desired configuration.
   For example, if you're using Flocker's ZFS storage backend you will have ZFS-specific agents running on each node in the cluster.


Control service
===============

The control service is the integration point between the desires of whoever is configuring the cluster, e.g. a human administrator or an orchestration framework, and the convergence agents that attempt to execute these desires.
In particular it controls the configuration of the cluster.

The service consists of three parts:

* A data storage system stores the configuration of the system.
* An external API allowing changes to the desired configuration, e.g. "create a new dataset on node A".
  The external API also allows checking the actual state of the cluster.
* An internal API used to communicate with the convergence agents.

All three of the above are encapsulated in a single server, for the moment limited to running on a single machine.


Convergence agents
==================

Convergence agents ensure that the state of the cluster eventually converges with the configuration.
They control the actual system state but are not be able to modify the configuration.

Convergence agents may be in charge of state on a specific node, e.g. a ZFS agent may be in charge of ZFS datasets.
Or they may be in charge of some cluster-wide state.
Each convergence agent runs a loop to converge the state is in charge of with the desired configuration.
The agent:

#. Checks the local state it is in charge of (e.g. by listing local ZFS filesystems).
#. Notifies the control service of the local state.
#. Calculates the actions necessary to make local state match desired configuration.
#. Executes these actions.
#. Starts the loop again.

For example, imagine the control service notifies the agent on node A that node A should have dataset D, and that as far as it knows no dataset D exists in the cluster.

#. The agent discovers there are no datasets on the node.
#. The agent tells the control service that there exist no datasets on the node.
#. The agent decides it needs to create dataset D, and does so.
#. The loop begins again - the agent discovers that dataset D exists on the node.
#. The agent tells the control service that dataset D exists on the node.
#. The agent sees that the node state matches the desired configuration, and realizes it doesn't need to do anything.
#. Etc.
