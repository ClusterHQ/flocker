Want to get your hands dirty? Skip ahead to the `tutorial`_.

Flocker
=======

Flocker is an open-source Container Data Volume Manager for your Dockerized applications.

By providing tools for data migrations, Flocker gives ops teams the tools they need to run containerized stateful services like databases in production.

Unlike a Docker data volume which is tied to a single server, a Flocker data volume, called a dataset, is portable and can be used with any container, no matter where that container is running.

Flocker manages Docker containers and data volumes together.
When you use Flocker to manage your stateful microservice, your volumes will follow your containers when they move between different hosts in your cluster.

You can also use Flocker to manage only your volumes, while continuing to manage your containers however you choose.


About Us
--------

Flocker is being developed by `ClusterHQ`_.
We are a small team of engineers with experience running distributed systems and many of us are core contributors to the `Twisted`_ project.

This project is under active development; version 1.0 was released on June 17th, 2015.
Contributions are welcome.
If you have any issues or feedback, you can `talk to us`_.
We're looking forward to working on this project with you.


Documentation
-------------

You can read more about `installing Flocker`_, follow a `tutorial`_ and learn about the `features of Flocker and its architecture`_ in the docs.


Feature Requests
----------------

If you have any feature requests or suggestions, we would love to hear about them.
Please add your ideas to our `UserVoice`_ forum, or file a `GitHub issue`_.


Tests
-----

Flocker's test suite is based on `unittest`_ and `Twisted Trial`_.
The preferred way to run the test suite is using the command ``trial flocker``.
Flocker also includes a `tox`_ configuration to run the test suite in multiple environments and to run additional checks
(such as `flake8`_) and build the documentation with Sphinx.
You can run all of the tox environments using the command ``tox``.

Flocker is also tested using `continuous integration`_.

.. _ClusterHQ: https://clusterhq.com/
.. _Twisted: https://twistedmatrix.com/trac/
.. _installing Flocker: https://docs.clusterhq.com/en/latest/using/installing/index.html
.. _tutorial: https://docs.clusterhq.com/en/latest/using/tutorial/index.html
.. _features of Flocker and its architecture: https://docs.clusterhq.com/en/latest/introduction/index.html
.. _unittest: https://docs.python.org/2/library/unittest.html
.. _Twisted Trial: https://twistedmatrix.com/trac/wiki/TwistedTrial
.. _tox: https://tox.readthedocs.org/
.. _continuous integration: http://build.clusterhq.com/
.. _talk to us: http://docs.clusterhq.com/en/latest/gettinginvolved/contributing.html#talk-to-us
.. _flake8: https://pypi.python.org/pypi/flake8
.. _UserVoice: https://feedback.clusterhq.com/
.. _GitHub issue: https://github.com/clusterhq/flocker/issues
