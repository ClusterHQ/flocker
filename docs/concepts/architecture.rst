.. _architecture:

============================
Flocker Cluster Architecture
============================

This document describes the Flocker cluster's architecture.

The Flocker cluster is comprised of the following sets of services:

* :ref:`The control service <control-service>` exposes the :ref:`api`, with which you can manage and modify the configuration of your cluster.
* :ref:`Flocker agents <flocker-agents>` are installed on each node in the cluster, and are used to modify the node to match the desired configuration of your cluster.
* :ref:`The Flocker plugin for Docker <plugin>` is also installed on each node in your cluster if you want Flocker to manage your data volumes while using other tools such as Docker, Docker Swarm, or Mesos to manage your containers.

.. _control-service:

The Control Service
===================

The control service is the brain of Flocker.
It enables a user, or an automated orchestration framework, to monitor and modify the cluster state.

The control service accepts instructions either directly via the :ref:`api`, or via the Flocker CLI (which uses the API under the hood).

When the control service has an instruction, it sends commands to the :ref:`Flocker agents <flocker-agents>`, and recieves updates back.

The control service is installed on a single node in your cluster.

.. _flocker-agents:

Flocker Agents
==============

Flocker agents ensure that the state of the cluster eventually converges with the configuration.
They control the actual system state but cannot modify the configuration.

Each agent is solely responsible for some particular piece of state in the cluster, its local state.
Some Flocker agents may be in charge of state related to a specific node, e.g. a ZFS agent may be in charge of ZFS datasets on node A.
Others may be in charge of some cluster-wide state.
Multiple agents may run on a specific node depending on the cluster setup.

Each Flocker agent runs a loop to converge the local state it manages with the desired cluster configuration managed by the control service.
The agent:

#. Checks the local state it is in charge of (e.g. by listing local ZFS filesystems).
#. Notifies the control service of the local state.
#. Calculates the actions necessary to make local state match desired configuration.
#. Executes these actions.
#. Starts the loop again.

For example, imagine the control service notifies the agent on node A that node A should have dataset D, and that as far as it knows no dataset D exists in the cluster.

#. The agent discovers there are no datasets on the node.
#. The agent tells the control service that there exist no datasets on the node.
   The agent always reports its latest local state to the control service to ensure it is up-to-date, even if it may change in near future.
#. The agent decides it needs to create dataset D, and does so.
#. The loop begins again - the agent discovers that dataset D exists on the node.
#. The agent tells the control service that dataset D exists on the node.
#. The agent sees that the node state matches the desired configuration, and realizes it doesn't need to do anything.
#. Etc.

.. _plugin:

Flocker Plugin for Docker
=========================
