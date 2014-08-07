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
    * Follows the coding standard (Python's `PEP 8`_).

    * Includes appropriate documentation.

    * Has full test coverage (unit tests and functional tests).

    * The tests pass in the continuous integration system (`Buildbot`_).

    * Resolves the issue.

* The code reviewer can approve the pull request for merging as is, with some changes, or request changes and an additional review.

.. _Ultimate Quality Development System: https://twistedmatrix.com/trac/wiki/UltimateQualityDevelopmentSystem
.. _PEP 8: http://legacy.python.org/dev/peps/pep-0008/
.. _Buildbot: http://build.clusterhq.com/


Talk to us
==========

Have questions or need help?
Besides filing a `GitHub issue`_ with feature requests or bug reports you can also join us on the ``#clusterhq`` channel on the ``irc.freenode.net`` IRC network or on the `flocker-users Google Group`_.

.. _GitHub issue: https://github.com/ClusterHQ/flocker/issues
.. _flocker-users Google Group: https://groups.google.com/forum/?hl=en#!forum/flocker-users

Development environment
=======================

* To run the complete test suite you will need `ZFS`_, `geard`_ and `docker`_ installed.
  ``geard`` requires an operating system with ``systemd``.
  The recommended way to get an environment with these installed is to use the included ``Vagrantfile`` which will create a pre-configured Fedora 20 virtual machine.
  Vagrant 1.6.2 or later is required.
  Once you have Vagrant installed (see the `vagrant documentation <http://docs.vagrantup.com/>`_) you can run the following to get going::

   $ vagrant up
   $ vagrant ssh

* You will need Python 2.7 and a recent version of PyPy installed on your development machine.
* If you don't already have ``tox`` on your development machine, you can install it and other development dependencies (ideally in a ``virtualenv``) by doing::

    $ python setup.py install .[doc,dev]

.. _ZFS: http://zfsonlinux.org
.. _geard: https://openshift.github.io/geard/
.. _docker: https://www.docker.com/


Running tests
=============

You can run all unit tests by doing::

   $ tox

Functional tests require ``ZFS``, ``geard`` and ``docker`` to be installed and in the case of the latter two running as well.
In addition, ``tox`` needs to be run as root::

   $ sudo tox

Since these tests involve global state on your machine (filesystems, iptables, docker containers, etc.) we recommend running them in the development Vagrant image.


Documentation
=============

Documentation is generated using `Sphinx`_ and stored in the ``docs/`` directory.
You can build it individually by running::

    $ tox -e sphinx

You can view the result by opening ``docs/_build/html/index.html`` in your browser.

.. _Sphinx: http://sphinx-doc.org/


Requirements for contributions
==============================

1. All code must have unit test coverage and to the extent possible functional test coverage.

   Use the coverage.py tool with the ``--branch`` option to generate line and branch coverage reports.
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

4. Add your name (in alphabetical order) to the ``AUTHORS.rst`` file.


Project development process
===========================

The core development team uses GitHub issues to track planned work.
Issues are organized by release milestones, and then by subcategories:

Backlog
    Issues we don't expect to do in the release.
    These issues don't have any particular category label.
    All issues start in the backlog when they are filed.
    The requirements for an issue must be completely specified before it can move out of the backlog.

Design
    Issues that we expect to work on soon.
    This is indicated by a ``design`` label.
    A general plan for accomplishing the requirements must be specified on the issue before it can move to the *Ready* state.
    The issue is assigned to the developer working on the plan.
    When there is a proposed plan the ``review`` label is added to the issue (so that it has both ``design`` and ``review``).

Ready
    Issues that are ready to be worked on.
    This is indicated by a ``ready`` label.
    Issues can only be *Ready* after they have been in *Design* so they include an implementation plan.
    When someone starts work on an issue it is moved to the *In Progress* category
    (the ``ready`` keyword is removed and the ``in progress`` label is added).

In Progress
    Such issues are assigned to the developer who is currently working on them.
    This is indicated by an ``in progress`` label.
    When the code is ready for review a new pull request is opened.
    The pull request is added to the *Review* category.

Ready for Review
    An issue or pull request that includes work that is ready to be reviewed.
    This is indicated by a ``review`` label.
    Issues can either be in design review (``design`` and ``review``) or final review (just ``review``).
    A reviewer can move a design review issue to *Ready* (to indicate the design is acceptable) or back to *Design* (to indicate it needs more work).
    A reviewer can move a final review issue to *Approved* (to indicate the work is acceptable) or back to *In Progress* (to indicate more work is needed).

Passed Review
    A pull request that has some minor problems that need addressing, and can be merged once those are dealt with and all tests pass.
    This is indicated by an ``accepted`` label.

Done
    Closed issues and pull requests.

Blocked
    Issues that can't be worked on because they are waiting on some other work to be completed.
    This is indicated by a ``blocked`` label.



You can see the current status of all issues and pull requests by visiting https://waffle.io/clusterhq/flocker.
In general issues will move from *Backlog* to *Design* to *Ready* to *In Progress*.
An in-progress issue will have a branch with the issue number in its name.
When the branch is ready for review a pull request will be created in the *Review* category.
When the branch is merged the corresponding pull requests and issues will be closed.


Steps to contribute code
^^^^^^^^^^^^^^^^^^^^^^^^

Github collaborators can participate in the development workflow by changing the labels on an issue.
Github lets non-collaborators create new issues and pull requests but it does not let them change labels.
If you are not a collaborator you may seek out assistances from a collaborator to set issue labels to reflect the issue's stage.

1. Pick the next issue in the *Ready* category.
   Drag it to the *In Progress* column in Waffle (or change the label from ``ready`` to ``in progress`` in GitHub).

2. Create a branch from master with a name including a few descriptive words and ending with the issue number, e.g. ``add-thingie-123``.

3. Resolve the issue by making changes in the branch.

4. Submit the issue/branch for review.
   Create a pull request on GitHub for the branch.
   The pull request should include a ``Fixes #123`` line referring to the issue that it resolves (to automatically close the issue when the branch is merged).
   Make sure Buildbot indicates all tests pass.

5. Address any points raised by the reviewer.
   If a re-submission for review has been requested, change the label from ``in progress`` to ``review`` in GitHub`` (or drag it to the *Ready for Review* column in Waffle) and go back to step 4.

6. Once it is approved, merge the branch into master by clicking the ``Merge`` button.


Steps to contribute reviews
^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Pick a pull request in GitHub/Waffle that is ready for review (``review`` label/*Review* category).

2. Use the continuous integration information in the PR to verify the test suite is passing.

3. Verify the code satisfies the Requirements for Contribution (see above).

4. Verify the change satisfies the requirements specified on the issue.

5. Think hard about whether the code is good or bad.

6. Leave comments on the GitHub PR page about any of these areas where you find problems.

7. Leave a comment on the GitHub PR page explicitly approving or rejecting the change.
   If you accept the PR and no final changes are required then use the GitHub merge button to merge the branch.
   If you accept the PR but changes are needed move it to the *Review Passed* column in Waffle or change its label from ``review`` to ``approved``.
   If you do not accept the PR move it to the *In Progress* column in Waffle or change its label from ``review`` to ``in progress``.
