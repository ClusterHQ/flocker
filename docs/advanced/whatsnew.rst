==========
What's New
==========

.. note:: If you already have a tutorial environment from a previous release see :ref:`upgrading-vagrant-environment`.


Next Release
============

* ``geard`` is no longer used to manage Docker containers.
* Moving volumes between nodes is now done with a :doc:`two-phase push<./clustering>` that should dramatically decrease application downtime when moving large amounts of data.
* Added support for environment variables in the :doc:`application configuration<./configuration>`.
* Added basic support for links between containers in the :doc:`application configuration<./configuration>`.
* Added support for `Fig`_ compatible application configuration files.


v0.1
====

Everything is new since this is our first release.


Known Limitations
=================

* This release is not ready for production and should not be used on publicly accessible servers or to store data you care about.
  Backwards compatibility is not a goal yet.
* Changes to the application configuration file will often not be noticed by ``flocker-deploy``, and there is no way to delete applications or volumes.
  Choose new names for your applications if you are making changes to the application configuration.

You can learn more about where we might be going with future releases by:

* Stopping by the ``#clusterhq`` channel on ``irc.freenode.net``.
* Visiting our GitHub repository at https://github.com/ClusterHQ/flocker.
* Reading :doc:`../roadmap/index`.

.. _`Fig`: http://www.fig.sh/yml.html
