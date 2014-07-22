.. Flocker documentation master file, created by
   sphinx-quickstart on Mon Apr 28 14:54:33 2014.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Flocker Documentation
=====================

Flocker is a volume manager and multi-host Docker cluster.
With it you can control your data using the same tools you use for your stateless applications.
This means that you can run your databases, queues and key-value stores in Docker and move them around as easily as the rest of your app.

With Flocker's command line tools and a simple configuration language, you can deploy your Docker-based applications onto one or more hosts.
Once deployed, your applications will have access to the volumes you have configured for them.
Those volumes will follow your containers when you use Flocker to move them between different hosts in your Flocker cluster.

Contents:

.. toctree::
   :maxdepth: 2

   installation
   tutorial/index
   flocker-intro/index
   whatsnew
   usage
   configuration
   volume/index
   routing/index
   roadmap/index
   infrastructure/index
   contributing
   authors


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

