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

Here’s how you can control Flocker:

.. toctree::
   :maxdepth: 2

   config/index
   plugin/index

Additionally, this section contains information about how to administer Flocker, a tutorial, and some examples:

.. toctree::
   :maxdepth: 2

   administering/index
   tutorial/index
   examples/apps
   examples/features
