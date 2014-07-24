.. _faqs:

FAQ
=============

.. contents::
    :local:
    :backlinks: none
	
Flocker is under active deployment and we receive a lot of questions about how this or that will be done in a future release.  You can find these questions in the Future section below.  You can also view `ideas for future releases`_  and `user stories for upcoming features`_.

If you want to get involved in a discussion about a future release or have a question about Flocker today, get in touch on our IRC #clusterhq or .. _the flocker Google group: https://groups.google.com/forum/#!forum/flocker-users.

Future / ZFS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If I clone a 2GB database five times, won't I need a really large server with 10 GB of disk?
**************************************************************************************************************

Thankfully no.  
This is where ZFS makes things really cool. 
Each clone is essentially free until the clone is modified. 
This is because ZFS is a copy-on-write filesystem, so a clone is just a set of block pointers. 
It's only when a block is modified that the data is copied, so a 2GB database that is cloned five times still just uses 2GB of disk space until a copy is modified.
That means, when the database is modified, only the changes are written to disk, so your are only storing the net new data.
This also makes it really fast to create database clones.


If I clone a database five times, how does maintaining five different versions of the database work? 
**************************************************************************************************************

The idea will be that cloning the app and the database together in some sense allows the containers to maintain what we call independent "links" between 10 instances of the app server (deployed at different staging URLs) and the respective 10 different instances of the cloned database. 
This works because eg port 3306 inside one app server gets routed via an ephemeral port on the host(s) to 3306 inside the corresponding specific instance of the database.

The upshot if which is that you shouldn't need to change the apps at all, except to configure each clone with a different URL.

Future / Integrations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

How does Flocker integrate with Kubernetes/Mesos/Deis/CoreOS/my favorite orchestration framework?
**************************************************************************************************************
Over time, we hope that Flocker becomes the de facto way for managing storage volumes with your favorite orchestration framework.  
We are interested in expanding libswarm to include support for filesystems and are talking with the various open source projects about the best way to collaborate on storage and networking for volumes. 
If you'd like work with us on integration, get in touch on our IRC #clusterhq or `the flocker Google group`.
You can also submit an issue or a pull request if you have a specific integration that you'd like to propose.


.. _ideas for future releases: https://github.com/ClusterHQ/flocker/blob/master/docs/roadmap/index.rst
.. _user stories for upcoming features: [link]
.. _the flocker Google group: https://groups.google.com/forum/#!forum/flocker-users