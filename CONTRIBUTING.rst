=======================
Contributing to Flocker
=======================

Introduction
============

ClusterHQ develops software using a variation of the `Ultimate Quality Development System`_.

* Each unit of work is defined in an issue in the issue tracker and developed on a branch.
* Code is written using test-driven development.
* The issue is closed by merging the branch (via a GitHub pull request).
* Before a branch is merged it must pass code review.
* The code reviewer ensures that the pull request:
    * Follows the coding standard (Python's PEP 8).
    * Includes appropriate documentation.
    * Has full test coverage (unit tests and functional tests).
    * The tests pass in the continuous integration system (Buildbot).
    * Resolves the issue.
* The code reviewer can approve the pull request for merging as is, with some changes, or request changes and an additional review.

.. _Ultimate Quality Development System: https://twistedmatrix.com/trac/wiki/UltimateQualityDevelopmentSystem
.. _PEP 8: http://legacy.python.org/dev/peps/pep-0008/


Development requirements
========================

* To run the complete test suite you will need `ZFS`_, `geard`_ and `docker`_ installed.
  ``geard`` requires an operating system with ``systemd``.
  The easiest way to get going with these is to use our Vagrant image::

   # XXX LINK TO UPDATED LOCATION
   $ vagrant init tomprince/flocker-dev
   $ vagrant up
   $ vagrant ssh

* You will need Python 2.7 and a recent version PyPy installed on your machine.
* If you don't already have ``tox`` on your machine, you can install it and other development dependencies (ideally in a ``virtualenv``) by doing::

    $ python setup.py install .[dev]

.. _ZFS: http://zfsonlinux.org
.. _geard: https://openshift.github.io/geard/
.. _docker: https://www.docker.com/


Running tests
=============

You can run all unit tests by doing::

   $ tox

Functional tests require ``ZFS``, ``geard`` and ``docker`` to be installed and in the case of the latter two running as well.
In addition, ``tox`` needs to be run as root.

   $ sudo tox

Since these tests involve global state on your machine (filesystems, iptables, docker containers, etc.) we recommend running them in the development Vagrant image.


Project development process
===========================

The core development team uses GitHub issues to track planned work.
Issues are organized by release milestones, and then by subcategories:

Ready
    Issues that are ready to be worked on.
    This is indicated by a ``ready`` label.
    When someone starts work on an issue it is moved to the *In Progress* category.

In Progress
    Such issues are assigned to the developer who is currently working on them.
    When the code is ready for review a new pull request is opened.
    The pull request is added to the *Review* category.

Review
    A pull request that is ready to be reviewed.
    A reviewer can move it to the *In Progress* category or the *Approved* category.

Passed Review
    A pull request that has some minor problems that need addressing, and can be merged once those are dealt with and all tests pass.

Done
    Closed issues and pull requests.

Blocked
    Issues that can't be worked on because they are waiting on some other work to be completed.
    This is indicated by a ``blocked`` label.

Backlog
    Issues we don't expect to do in the release.
    These issues don't have any particular category label.


You can see the current status of all issues and pull requests by visiting https://waffle.io/hybridlogic/flocker.
In general issues will move from *Backlog* to *Ready* to *In Progress*.
An in-progress issue will have a branch with the issue number in its name, e.g. ``fix-thingie-123``.
When the branch is ready for review a pull request will be created in the *Review* category.
When the pull request is merged its commit message should include a ``Fixes #123`` line referring to the relevant issue that it is resolved and the issue will be automatically closed and move into the *Done* category.


Steps to contribute code - internal contributors
================================================

    1. Pick the next issue in `the tracker <https://www.pivotaltracker.com/n/projects/1069998>`_.
       Click the ``Start`` button on the issue in `the tracker`_.

    2. Create a branch from master with a name including a few descriptive words and ending with the issue number.

    3. Resolve the issue by making changes in the branch.

    4. Use the continuous integration system to verify the test suite is passing (TODO: Set up continuous integration; automate this step).

    5. Submit the issue/branch for review.
       Create a pull request on GitHub for the branch.
       Link to the issue in the tracker.
       Create a reciprocal link on the issue in `the tracker`_.
       Click the ``Deliver`` button on the issue in `the tracker`_.

    6. Address any points raised by the reviewer.
       If requested, go back to step 5.

    7. Merge the branch into master (TODO: Determine if this means clicking the green button on the github PR page).


Steps to contribute code - external contributors
================================================


Steps to contribute reviews
===========================

    1. Pick an issue in `the tracker`_ that has been submitted for review.

    2. Use the continuous integration system to verify the test suite is passing (TODO: Set up continuous integration; automate this step).

    3. Verify the code satisfies the Requirements for Contribution (see below).

    4. Verify the change satisfies the requirements specified on the issue.

    5. Think hard about whether the code is good or bad.

    6. Leave comments on the github PR page about any of these areas where you find problems.

    7. Leave a comment on the github PR page explicitly approving or rejecting the change.
       If you accept the PR and no final changes are required then use the GitHub merge button to merge the branch.
       If you accept the PR (whether you merge it or not) click the ``Accept`` button on the issue in `the tracker`_.
       If you do not accept the PR click the ``Reject`` button on the issue in `the tracker`_.

Requirements for Contributions
==============================

    * All code must have unit test coverage.
      Use the coverage.py tool with the `--branch` option to generate line and branch coverage reports.
      This report can tell you if you missed anything.
      It does not necessarily catch everything though.
      Treat it as a helper but not the definitive indicator of success.
      Practice test-driven development to ensure all code has test coverage.

    * All code must have documentation.
      Modules, functions, classes, and methods must be documented (even if they are private or nested).
      Function parameters and object attributes must be documented (even if they are private).

    * All user-facing tools must have documentation.
      Document tool usage as part of big-picture documentation.
      Identify useful goals the user may want to accomplish and document tools within the context of accomplishing those goals.
