=======
flocker
=======
probably a replication-based failover product

Development
-----------

Tests
~~~~~

Flocker's test suite is based on `unittest`_ and `Twisted Trial`_.
The preferred way to run the test suite is using the command `trial flocker`.
Flocker also includes a `tox`_ configuration to run the test suite in multiple environments and to run additional checks
(such as flake8 and build the documentation with Sphinx).
You can run all of the tox environments using the command `tox`.

Flocker is also tested using `continuous integration`_.

.. _unittest: https://docs.python.org/2/library/unittest.html
.. _Twisted Trial: https://twistedmatrix.com/trac/wiki/TwistedTrial
.. _tox: https://tox.readthedocs.org/
.. _continuous integration: http://build.flocker.hybridcluster.net/
