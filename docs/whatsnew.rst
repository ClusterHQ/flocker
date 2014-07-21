==================
What's New in v0.1
==================

Introducing Flocker
===================

The most notable feature in our first release is the ability to move data along with containers.
By default Docker and therefore Docker orchestration frameworks are not well-suited to running stateful applications that store data on disk: moving a container from one machine to another does not move the data along with it.
Standard advice is therefore not to use Docker for any applications that rely on disk storage for anything beyond logging.
Needless to say this is a rather significant restriction.

Flocker in contrast is all about supporting your on-disk data.
When you move an application from machine A to machine B the data in the Flocker volume is moved along with your container.
This is done on the filesystem level by utilizing `ZFS`_.

.. _ZFS: https://en.wikipedia.org/wiki/ZFS


Known Limitations
=================

* This release is not ready for production and should not be used on publicly accessible servers or to store data you care about.
  Backwards compatibility is not a goal yet.
* Changes to the application configuration file will often not be noticed by ``flocker-deploy``, and there is no way to delete applications or volumes.
  Choose new names for your applications if you are making changes to the application configuration.

You can learn more about where we might be going with future releases by:

* Stopping by the ``#clusterhq`` channel on ``irc.freenode.net``.
* Visiting our GitHub repository at https://github.com/ClusterHQ/flocker
* Reading :doc:`roadmap/index`.
