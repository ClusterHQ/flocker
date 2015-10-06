====================================
Enabling the Flocker control service
====================================

CentOS 7
========

.. task:: enable_flocker_control centos-7
   :prompt: [root@control-node]#


Ubuntu
======

.. task:: enable_flocker_control ubuntu-14.04
   :prompt: [root@control-node]#

======================
Firewall Configuration
======================

The control service needs to accessible remotely:

* The REST API listens on TCP port 4523, and
* on TCP port 4524 for connections from ``flocker-dataset-agent`` and ``flocker-container-agent`` processes on all nodes.

``flocker-control`` listens on all local IPv4 and addresses.

The ``clusterhq-flocker-node`` package includes firewall configuration files for your operating system.
The package includes a post-install script which will configure and restart your firewall automatically.

* On Ubuntu-14.04, the firewall is managed by `UFW`_ and the configuration files are in ``/etc/ufw/applications.d``.
* On Centos-7, the firewall is managed by `FirewallD`_ and the configuration files are in ``/usr/lib/firewalld``.
* On AWS, an external firewall is used instead, which will need to be configured manually.

.. note:: The firewall will be reconfigured automatically after the ``clusterhq-flocker-node`` package is installed.

.. _FirewallD documentation: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/Security_Guide/sec-Using_Firewalls.html
.. _UFW documentation: https://help.ubuntu.com/community/UFW
