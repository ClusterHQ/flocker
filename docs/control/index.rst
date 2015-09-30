.. _controlling-flocker:

===================
Controlling Flocker
===================

You can control Flocker in a number of ways.
Find out which way is best for you.

Flocker lives on your nodes alongside Docker.
Each node where Docker is installed will have a Flocker agent as well.
The Flocker agents are controlled by the Flocker control service which is installed on just one node (usually a dedicated node).
The Flocker control service is controlled via API endpoints, either directly or indirectly.

You can control Flocker in the following ways:

* From the command line, using the Flocker CLI tools.
* The Flocker plugin for Docker is installed on each node where a Flocker agent is running, and enables you to control Flocker using the Docker command line tools.
* Using the :ref:`Flocker API <api>` directly.

The following topics go into more detail about how you can control Flocker, including information about how to administer Flocker, a tutorial, and some examples:

.. toctree::
   :maxdepth: 2

   config/index
   plugin/index
   administering/index
   tutorial/index
   examples/apps
   examples/features
