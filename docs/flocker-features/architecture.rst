.. _architecture:

============================
Flocker Cluster Architecture
============================

The Flocker cluster is comprised of the following sets of services:

* :ref:`The Flocker control service <control-service>` exposes the :ref:`api`, with which you can manage and modify the configuration of your cluster.
* :ref:`Flocker agents <flocker-agents>` are installed on each node in the cluster, and are used to modify the node to match the desired configuration of your cluster.
* :ref:`The Flocker plugin for Docker <plugin>` is also installed on each node in your cluster if you want Flocker to manage your data volumes, while using other tools such as Docker, Docker Swarm, or Mesos to manage your containers.

.. XXX FLOC-3598 add an architecture image here 

.. _control-service:

Flocker Control Service
=======================

The control service is the brain of Flocker.
It enables a user, or an automated orchestration framework, to monitor and modify the cluster state.

The control service accepts instructions either directly via the :ref:`api`, or via the Flocker CLI (which uses the API under the hood).

When the control service receives an instruction, it sends commands to the :ref:`Flocker agents <flocker-agents>`, and receives updates back.

The control service is installed on a single node in your cluster.

.. _flocker-agents:

Flocker Agents
==============

Flocker agents ensure that the state of the cluster matches the configuration.
They control the actual system state, but cannot modify the configuration.

Flocker agents can:

* be responsible for a particular piece of state in the cluster, known as the local state.
* be in charge of state related to a specific node.
* be in charge of cluster-wide state.

Multiple agents can also run on a specific node depending on the cluster setup.

Each Flocker agent runs the following loop to converge the local state it manages with the desired cluster configuration, as managed by the Flocker control service:

#. Checks the local state that it is in charge of.
#. Notifies the control service of the local state.
#. Calculates the actions necessary to make local state match desired configuration.
#. Executes these actions.
#. Starts the loop again.

For example, the following will occur if the control service notifies the agent on node A that it should have dataset D, and that dataset D does not currently exist in the cluster:

#. The agent discovers there are no datasets on the node.
#. The agent tells the control service that no datasets on the node exist.
   The agent will always report its latest local state to the control service to ensure it is up-to-date, even if it may change in near future.
#. The agent decides it needs to create dataset D, and does so.
#. The loop begins again - the agent discovers that dataset D now does exist on the node.
#. The agent tells the control service that dataset D exists on the node.
#. The agent sees that the node state matches the desired configuration, and knows that no action is required.
#. Starts the loop again.

.. _plugin:

Flocker Plugin for Docker
=========================

The Flocker plugin for Docker enables you to run containers with named volumes without worrying which server your data is on.

The plugin will create or move the volumes in place as necessary.

The Flocker plugin for Docker operates on the ``name`` passed to Docker in the ``docker run`` command and associates it with a Flocker dataset with the same name (i.e. with metadata ``name=foo``).

There are three main cases which the plugin handles:

* If the volume does not exist at all on the Flocker cluster, it is created on the host which requested it.
* If the volume exists on a different host, it is moved in-place before the container is started.
* If the volume exists on the current host, the container is started straight away.

Multiple containers can use the same Flocker volume (by referencing the same volume name, or by using Docker's ``--volumes-from``) so long as they are running on the same host.

The plugin is installed on each node in your cluster, and depends on Docker 1.8 or later.
