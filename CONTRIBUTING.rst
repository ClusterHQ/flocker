.. _contribute:

=======================
Contributing to Flocker
=======================

Introduction
============

ClusterHQ develops software using test-driven development, code reviews and per-issue branches.

* Each unit of work is defined in an issue in the issue tracker and developed on a branch.

* Code is written using test-driven development.

* The issue is closed by merging the branch (via a GitHub pull request).

* Before a branch is merged it must pass code review.

* The code reviewer ensures that the pull request:
    * Follows the coding standard (Python's `PEP 8`_).

    * Includes appropriate documentation.

    * Has full test coverage (unit tests and functional tests).

    * The tests pass in the continuous integration system (`Buildbot`_).

    * Resolves the issue.

* The code reviewer can approve the pull request for merging as is, with some changes, or request changes and an additional review.

.. _PEP 8: http://legacy.python.org/dev/peps/pep-0008/
.. _Buildbot: http://build.clusterhq.com/


.. _talk-to-us:

Talk to Us
==========

Have questions or need help?

* If you want to follow our development plans, our main issue tracker is `JIRA`_.
* You can open an account there to file issues, but we're also happy to accept `GitHub issues`_ with feature requests or bug reports and :ref:`security issues should be reported directly to our security team<reporting-security-issues>`.
* You can also join us on the ``#clusterhq`` channel on the ``irc.freenode.net`` IRC network or on the `flocker-users Google Group`_.

.. _GitHub issues: https://github.com/ClusterHQ/flocker/issues
.. _flocker-users Google Group: https://groups.google.com/forum/?hl=en#!forum/flocker-users


Development Environment
=======================

You will need Python 2.7 (and optionally a recent version of PyPy) installed on your development machine.
To run the complete test suite you will also need `ZFS`_ and `Docker`_ installed.

The recommended way to get an environment with these installed is to use Vagrant to run a pre-configured Flocker development virtual machine.

First, clone the Flocker repository on your local machine:

.. code-block:: console

   $ git clone https://github.com/ClusterHQ/flocker.git
   $ cd flocker

Vagrant 1.6.2 or later is required.
Once you have Vagrant installed (see the `Vagrant documentation <https://docs.vagrantup.com/v2/>`_) you can run the following to get going:

.. code-block:: console

   $ vagrant up
   $ vagrant ssh

The ``flocker`` directory created above will be shared in the virtual machine at ``/vagrant``.
Install Flocker's development dependencies in a ``virtualenv`` by running the following commands:

.. code-block:: console

   $ cd /vagrant
   $ mkvirtualenv flocker
   $ pip install --editable .[dev]

.. _ZFS: http://zfsonlinux.org
.. _Docker: https://www.docker.com/


Running Tests
=============

You can run all unit tests by doing:

.. code-block:: console

   $ tox

You can also run specific tests in a specific environment:

.. code-block:: console

   $ tox -e py27 flocker.control.test.test_httpapi

Functional tests require ``ZFS`` and ``Docker`` to be installed and, in the case of Docker, running.
In addition, ``tox`` needs to be run as root:

.. code-block:: console

   $ sudo tox

Since these tests involve global state on your machine (filesystems, ``iptables``, Docker containers, etc.) we recommend running them in the development Vagrant image.


Documentation
=============

Documentation is generated using `Sphinx`_ and stored in the ``docs/`` directory.
You can build it individually by running:

.. code-block:: console

   $ tox -e sphinx

You can view the result by opening ``docs/_build/html/index.html`` in your browser.

.. _Sphinx: http://sphinx-doc.org/


Contributing to Flocker
=======================

At a minimum you can simply submit a GitHub Pull Request with your changes.
In order to maximize your chances of getting your code accepted, and to keep you from wasting time:

* Discuss your ideas with us in advance in a `JIRA`_ or GitHub issue.
* Explain the purpose of your PR, and why these changes are necessary.
* Limit your PR to fixing a single problem or adding a single feature.
* See the merge requirements below for details about our testing and documentation requirements.

Make sure your PR adds your name to ``AUTHORS.rst`` if you've never contributed to Flocker before.

Once your pull request is merged, as a small thank you for contributing to Flocker we'd like to send you some ClusterHQ swag.
Just send an email to thankyou@clusterhq.com with your t-shirt size, mailing address and a phone number to be used only for filling out the shipping form.
We'll get something in the mail to you.


Merge Requirements
^^^^^^^^^^^^^^^^^^

While we're happy to look at contributions in any state as GitHub PRs, the requirements below will need to be met before code is merged.

1. All code must have unit test coverage and to the extent possible functional test coverage.

   Use the ``coverage.py`` tool with the ``--branch`` option to generate line and branch coverage reports.
   This report can tell you if you missed anything.
   It does not necessarily catch everything though.
   Treat it as a helper but not the definitive indicator of success.
   You can also see coverage output in the Buildbot details link of your pull request.
   Practice test-driven development to ensure all code has test coverage.

2. All code must have documentation.

   Modules, functions, classes, and methods must be documented (even if they are private).
   Function parameters and object attributes must be documented (even if they are private).

3. All user-facing tools must have documentation.

   Document tool usage as part of big-picture documentation.
   Identify useful goals the user may want to accomplish and document tools within the context of accomplishing those goals.
   Documentation should be as accessible and inclusive as possible.
   Avoid language and markup which assumes the ability to precisely use a mouse and keyboard, or that the reader has perfect vision.
   Create alternative but equal documentation for the visually impaired, for example, by using alternative text on all images.
   If in doubt, particularly about markup changes, use http://achecker.ca/checker/index.php and fix any "Known Problems" and "Likely Problems".


Project Development Process
===========================

The core development team uses a `JIRA`_ workflow to track planned work.
Issues are organized by sprints, and can reside in various states:

Backlog
    All issues start in the backlog when they are filed.

Design Backlog
    The issue requires a design, and will be worked on soon.

Design
    The issue is currently being designed.

Design Review Ready
    The design is ready for review.
    This often involves submitting a GitHub pull request with a sketch of the code.

Code Backlog
    The design has been approved and is ready to code.

Coding
    The issue is currently being coded.

Code Review Ready
    The code is ready for review.
    This typically involves submitting a GitHub pull request.

Code Review
    The code is being reviewed.

Done
    The issue has been closed.
    Some final work may remain to address review comments; once this is done and the branch is merged the GitHub PR will be closed.


.. _reporting-security-issues:

Reporting Security Issues
=========================

Please report security issues by emailing security@clusterhq.com.

Flocker bugs should normally be :ref:`reported publicly<talk-to-us>`, but due to the sensitive nature of security issues, we ask that they not be publicly reported in this fashion.

Instead, if you believe you have found something in Flocker (or any other ClusterHQ software) which has security implications, please send a description of the issue via email to security@clusterhq.com.
Your message will be forwarded to the ClusterHQ security team (a small group of trusted developers) for triage and it will not be publicly readable.
Once you have submitted an issue via email, you should receive an acknowledgment from a member of the security team within 48 hours, and depending on the action to be taken, you may receive further follow up emails.

.. _JIRA: https://clusterhq.atlassian.net/secure/Dashboard.jspa
