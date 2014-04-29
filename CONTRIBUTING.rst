=======================
Contributing to Flocker
=======================

Steps to Contribute Code
========================

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

Steps to Contribute Reviews
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
