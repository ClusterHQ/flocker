====================
Configuration Stores
====================

The :ref:`Flocker control service <control-service>` maintains information about the state of the cluster and must store it across restarts. The default persistence mechanism for control service data is to save it as a file on the control node.

By introducing a configuration store plugin architecture, Flocker opens up the possibility of using a variety of persistence mechanisms. Using a network-based configuration store is an important step toward building a highly available Flocker control service.


Listing and activating configuration stores
===========================================

Configuration store plugins are added to Flocker as a community effort. Run ``flocker-control --help`` for details on which configuration stores are supported by your Flocker distribution, and how to use them.

Activating a specific configuration store requires changing the command line arguments in the flocker-control startup script. For example when running flocker-control under systemd on CentOS 7:

#. Modify ``/usr/lib/systemd/system/flocker-control.service`` and add the ``--configuration-store-plugin`` parameter::

    ExecStart=/usr/sbin/flocker-control --configuration-store-plugin=myplugin --extra-pluginvar=foo
  
#. Execute::
    
    systemctl daemon-reload
    systemctl restart flocker-control


Directory configuration store
=============================

The default. Saves the cluster state as a flat file in a configurable location, by default in ``/var/lib/flocker``. Example::


    flocker-control --data-path=/path/to/share


ZooKeeper configuration store
=============================

Saves the configuration in `ZooKeeper <https://zookeeper.apache.org/>`_ , a highly available key-value store designed for maintaining configuration information. Example::

    flocker-control --configuration-store-plugin=zookeeper --zookeeper-hosts=192.168.0.1:2181,192.168.0.2:2181,192.168.0.3:2181


Helper script
-------------

A bundled tool, `flocker-zk`, helps migrate and examine configuration data held in ZooKeeper.


Log entries
-----------

The log message type `flocker:control:store:zookeeper` identifies entries originating from this plugin.
