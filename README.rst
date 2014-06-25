=======
Flocker
=======
Flocker is a volume manager and multi-host Docker container orchestration tool.
With it you can control your data using the same tools you use for your stateless applications.
This means that you can run your databases, queues and key-value stores in Docker and move them around as easily as the rest of your app.

With Flocker's command line tools and a simple configuration language, you can deploy your Docker-based applications onto one or more hosts.
Once deployed, your applications will have access to the volumes you have configured for them.
Those volumes will follow your containers when you use Flocker to move them between different hosts in your Flocker cluster.

Flocker is being developed by `ClusterHQ`_.  
We are a small team of engineers with experience running distributed systems and many of us are core contributors to the Twisted Python project.

This project is under active development and version 0.1 will be released soon. You shouldn't use it in production.
We're looking forward to developing on this project with you. 

Documentation
-----------
You can read more about the features of Flocker and its architecture in the docs.

Tests
~~~~~

Flocker's test suite is based on `unittest`_ and `Twisted Trial`_.
The preferred way to run the test suite is using the command `trial flocker`.
Flocker also includes a `tox`_ configuration to run the test suite in multiple environments and to run additional checks
(such as pyflakes and build the documentation with Sphinx).
You can run all of the tox environments using the command `tox`.

Flocker is also tested using `continuous integration`_.

.. _ClusterHQ: https://clusterhq.com/
.. _unittest: https://docs.python.org/2/library/unittest.html
.. _Twisted Trial: https://twistedmatrix.com/trac/wiki/TwistedTrial
.. _tox: https://tox.readthedocs.org/
.. _continuous integration: http://build.flocker.hybridcluster.net/


