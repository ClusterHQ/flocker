Want to get your hands dirty? Skip ahead to the `tutorial`_.

Flocker |coveralls|
===================

.. |coveralls| image:: https://coveralls.io/repos/ClusterHQ/flocker/badge.png
  :target: https://coveralls.io/r/ClusterHQ/flocker
  :alt: 'Buildbot build coverage status'

Flocker is a data volume manager and multi-host Docker cluster management tool.
With it you can control your data using the same tools you use for your stateless applications by harnessing the power of ZFS on Linux.
This means that you can run your databases, queues and key-value stores in Docker and move them around as easily as the rest of your app.

With Flocker's command line tools and a simple configuration language, you can deploy your Docker-based applications onto one or more Linux hosts.
Once deployed, your applications will have access to the volumes you have configured for them.
Those volumes will follow your containers when you use Flocker to move them between different hosts in your Flocker cluster.

Flocker is being developed by `ClusterHQ`_.
We are a small team of engineers with experience running distributed systems and many of us are core contributors to the `Twisted`_ project.

This project is under active development; version 0.1 was released on August 12th, 2014.
You shouldn't use it in production yet.
Contributions are welcome.
If you have any issues or feedback, you can `talk to us`_.
We're looking forward to working on this project with you.


Documentation
-------------

You can read more about `installing Flocker`_, follow a `tutorial`_ and learn about the `features of Flocker and its architecture`_ or `areas for potential future development`_ in the docs.


Tests
-----

Flocker's test suite is based on `unittest`_ and `Twisted Trial`_.
The preferred way to run the test suite is using the command ``trial flocker``.
Flocker also includes a `tox`_ configuration to run the test suite in multiple environments and to run additional checks
(such as `flake8`_) and build the documentation with Sphinx.
You can run all of the tox environments using the command ``tox``.

Flocker is also tested using `continuous integration`_.

.. _ClusterHQ: https://clusterhq.com/
.. _Twisted: https://twistedmatrix.com
.. _installing Flocker: https://docs.clusterhq.com/en/latest/indepth/installation.html
.. _tutorial: https://docs.clusterhq.com/en/latest/using/tutorial/index.html
.. _features of Flocker and its architecture: https://docs.clusterhq.com/en/latest/introduction.html
.. _areas for potential future development: https://docs.clusterhq.com/en/latest/roadmap/
.. _unittest: https://docs.python.org/2/library/unittest.html
.. _Twisted Trial: https://twistedmatrix.com/trac/wiki/TwistedTrial
.. _tox: https://tox.readthedocs.org/
.. _continuous integration: http://build.clusterhq.com/
.. _talk to us: http://docs.clusterhq.com/en/latest/gettinginvolved/contributing.html#talk-to-us
.. _flake8: https://pypi.python.org/pypi/flake8
