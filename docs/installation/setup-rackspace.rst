.. Single Source Instructions

================================
Setting Up Nodes Using Rackspace
================================

.. begin-body

You can get a Flocker cluster running using Rackspace.
You'll need to setup at least two nodes.

#. Create a new cloud server:

   * Visit https://mycloud.rackspace.com.
   * Click "Create Server".
   * Choose a supported Linux distribution (either RHEL 7, CentOS 7, Ubuntu 16.04 or Ubuntu 14.04) as your image.
   * Choose a Flavor.
     We recommend at least "8 GB General Purpose v1".
   * Add your SSH key.

#. SSH in:

   You can find the IP in the Server Details page after each node is created:

   .. prompt:: bash alice@mercury:~$

      ssh root@203.0.113.109

.. end-body
