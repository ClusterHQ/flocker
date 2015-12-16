.. _enabling-control-service:

====================================
Enabling the Flocker Control Service 
====================================

The control service is the brain of Flocker; it can live anywhere in your cluster, and enabling it is an essential step in setting up your cluster.

For more information about the control service, see :ref:`architecture`.

CentOS 7
========

.. task:: enable_flocker_control centos-7
   :prompt: [root@control-node]#

The control service needs to be accessible remotely.
You will need to configure FirewallD to allow access to the control service HTTP API and for agent connections.
Note that on some environments, in particular AWS, the ``firewalld`` package is not installed and the ``firewall-cmd`` program will not be found.
If that is the case then just skip these commands.
Otherwise run:

.. task:: open_control_firewall centos-7
   :prompt: [root@control-node]#

For more details on configuring the firewall, see the `FirewallD documentation`_.

On AWS, an external firewall is used instead, which will need to be configured similarly.

Ubuntu
======

.. task:: enable_flocker_control ubuntu-14.04
   :prompt: [root@control-node]#

The control service needs to accessible remotely.
To configure ``UFW`` to allow access to the control service HTTP API, and for agent connections:

.. task:: open_control_firewall ubuntu-14.04
   :prompt: [root@control-node]#

For more details on configuring the firewall, see Ubuntu's `UFW documentation`_.

On AWS, an external firewall is used instead, which will need to be configured similarly.

.. _FirewallD documentation: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/Security_Guide/sec-Using_Firewalls.html
.. _UFW documentation: https://help.ubuntu.com/community/UFW