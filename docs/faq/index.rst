.. _faqs:

FAQ
===

.. contents::
    :local:
    :backlinks: none

Flocker is under active deployment and we receive a lot of questions about how this or that will be done in a future release.
You can find these questions in the Future Functionality section below.
You can also view :doc:`ideas for future versions of Flocker</roadmap/index>`.

If you want to get involved in a discussion about a future release or have a question about Flocker today, get in touch on our Freenode IRC channel ``#clusterhq`` or `the Flocker Google group`_.

ZFS
~~~

Flocker uses ZFS. What about the ZFS licensing issues?
******************************************************

There is a `good write up of the ZFS and Linux license issues`_ on the ZFS on Linux website.
In short, while ZFS won't be able to make it into mainline Linux proper due to licensing issues, "there is nothing in either license that prevents distributing it in the form of a binary module or in the form of source code."


But if ZFS isn't part of mainline Linux proper, it won't benefit from rigorous testing. How do you know it's stable?
********************************************************************************************************************


ZFS on Linux is already in use in companies and institutions all over the world to the tune of hundreds of petabytes of data.
We are also rigorously testing ZFS on Linux to make sure it is stable.
ZFS is production quality code.


Current Functionality
~~~~~~~~~~~~~~~~~~~~~

Which operating systems are supported?
**************************************

Flocker manages Docker applications and Docker runs on Linux, so Flocker runs on Linux.
However, you do not need to be running Linux on your development machine in order to manage Docker containers with the ``flocker-cli``.
See :ref:`installing-flocker-cli` for installation instructions for various operating systems.


Future Functionality
~~~~~~~~~~~~~~~~~~~~

How does Flocker integrate with Kubernetes / Mesos / Deis / CoreOS / my favorite orchestration framework?
*********************************************************************************************************

.. spelling::

   de
   facto

Over time, we hope that Flocker becomes the de facto way for managing storage volumes with your favorite orchestration framework.
We are interested in expanding libswarm to include support for filesystems and are talking with the various open source projects about the best way to collaborate on storage and networking for volumes.
If you'd like work with us on integration, get in touch on our Freenode IRC ``#clusterhq`` or `the Flocker Google group`_.
You can also submit an issue or a pull request if you have a specific integration that you'd like to propose.

If I clone a 2 GB database five times, won't I need a really large server with 10 GB of disk?
*********************************************************************************************

Thankfully no.
This is where ZFS makes things really cool.
Each clone is essentially free until the clone is modified.
This is because ZFS is a copy-on-write filesystem, so a clone is just a set of block pointers.
It's only when a block is modified that the data is copied, so a 2GB database that is cloned five times still just uses 2GB of disk space until a copy is modified.
That means, when the database is modified, only the changes are written to disk, so your are only storing the net new data.
This also makes it really fast to create database clones.


If I clone a database five times, how does maintaining five different versions of the database work?
****************************************************************************************************

The idea will be that cloning the app and the database together in some sense allows the containers to maintain what we call independent "links" between 10 instances of the app server (deployed at different staging URLs) and the respective 10 different instances of the cloned database.
This works because e.g. port 3306 inside one app server gets routed via an ephemeral port on the host(s) to 3306 inside the corresponding specific instance of the database.

The upshot if which is that you shouldn't need to change the apps at all, except to configure each clone with a different URL.


Security
~~~~~~~~

I think I've found a security problem! What should I do?
********************************************************

If you think you've found a security problem with Flocker (or any other ClusterHQ software), please send a message to security@clusterhq.com.
Your message will be forwarded to the ClusterHQ security team (a small group of trusted developers) for triage and it will not be publicly readable.

Due to the sensitive nature of security issues, we ask you not to send a message to one of the public mailing lists.
ClusterHQ has a policy for :ref:`reporting-security-issues` designed to minimize any damage that could be inflicted through public knowledge of a defect while it is still outstanding.

.. _good write up of the ZFS and Linux license issues: http://zfsonlinux.org/faq.html#WhatAboutTheLicensingIssue
.. _the Flocker Google group: https://groups.google.com/forum/#!forum/flocker-users
