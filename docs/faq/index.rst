.. _faqs:

FAQ
===

.. contents::
    :local:
    :backlinks: none

Flocker is under active deployment and we receive a lot of questions about how this or that will be done in a future release.

If you want to get involved in a discussion about a future release or have a question about Flocker today, get in touch on our Freenode IRC channel ``#clusterhq`` or `the Flocker Google group`_.

Functionality
~~~~~~~~~~~~~

Which operating systems are supported?
**************************************

Flocker manages Docker applications and Docker runs on Linux, so Flocker runs on Linux.
However, you do not need to be running Linux on your development machine in order to manage Docker containers with the ``flocker-cli``.
See :ref:`installing-flocker-cli` for installation instructions for various operating systems.

How does Flocker integrate with Kubernetes / Mesos / Deis / CoreOS / my favorite orchestration framework?
*********************************************************************************************************

.. spelling::

   de
   facto

Over time, we hope that Flocker becomes the de facto way for managing storage volumes with your favorite orchestration framework.
We are interested in expanding libswarm to include support for filesystems and are talking with the various open source projects about the best way to collaborate on storage and networking for volumes.
If you'd like work with us on integration, get in touch on our Freenode IRC ``#clusterhq`` or `the Flocker Google group`_.
You can also submit an issue or a pull request if you have a specific integration that you'd like to propose.

Security
~~~~~~~~

I think I've found a security problem! What should I do?
********************************************************

If you think you've found a security problem with Flocker (or any other ClusterHQ software), please send a message to security@clusterhq.com.
Your message will be forwarded to the ClusterHQ security team (a small group of trusted developers) for triage and it will not be publicly readable.

Due to the sensitive nature of security issues, we ask you not to send a message to one of the public mailing lists.
ClusterHQ has a policy for :ref:`reporting-security-issues` designed to minimize any damage that could be inflicted through public knowledge of a defect while it is still outstanding.

ZFS
~~~

Flocker uses ZFS in experimental configurations. What about the ZFS licensing issues?
**************************************************************************************

There is a `good write up of the ZFS and Linux license issues`_ on the ZFS on Linux website.
In short, while ZFS won't be able to make it into mainline Linux proper due to licensing issues, "there is nothing in either license that prevents distributing it in the form of a binary module or in the form of source code."


But if ZFS isn't part of mainline Linux proper, it won't benefit from rigorous testing. How do you know it's stable?
********************************************************************************************************************

Note that Flocker only uses ZFS in experimental configurations.
ZFS on Linux is already in use in companies and institutions all over the world to the tune of hundreds of petabytes of data.
We are also rigorously testing ZFS on Linux to make sure it is stable.
ZFS is production quality code.

.. _good write up of the ZFS and Linux license issues: http://zfsonlinux.org/faq.html#WhatAboutTheLicensingIssue
.. _the Flocker Google group: https://groups.google.com/forum/#!forum/flocker-users
