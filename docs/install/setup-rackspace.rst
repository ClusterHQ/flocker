.. _rackspace-install:

==============================================
Setting Up Flocker Ready Nodes Using Rackspace
==============================================

You can get a Flocker cluster running using Rackspace.
You'll need to setup at least two nodes.

#. Create a new cloud server:

   * Visit https://mycloud.rackspace.com
   * Click "Create Server".
   * Choose a supported Linux distribution (either CentOS 7 or Ubuntu 14.04) as your image.
   * Choose a Flavor.
     We recommend at least "8 GB General Purpose v1".
   * Add your SSH key

#. SSH in:

   You can find the IP in the Server Details page after it is created.

   .. prompt:: bash alice@mercury:~$

      ssh root@203.0.113.109

#. Follow the operating system specific installation instructions in :ref:`installing-flocker-node` for each node in your cluster.
