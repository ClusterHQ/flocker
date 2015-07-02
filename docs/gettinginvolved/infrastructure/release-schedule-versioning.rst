Release Schedule and Version Numbers
====================================

Goals
-----

The goals of the release schedule are to:

* Make new features and bug fixes available to users as quickly as possible.
* Practice releasing so that we are less likely to make mistakes.
* Improve the automation of releases through experience.

Schedule
--------

We will make a new release of Flocker each week.
This will proceed according to the :doc:`release-process`.
The releases will happen on Tuesday of each week.
If nobody is available in the ClusterHQ organization to create a release, the week will be skipped.

After each release is distributed, the engineer who performed the release will create issues for any improvements which could be made.
The release engineer should then spend 4-8 hours working on making improvements to release process.
If there is an issue that will likely take over 8 hours then they should consult the team manager before starting them.

.. _version-numbers:

Version Numbers
---------------

Released version numbers take the form of ``X.Y.Z``.
The current value of ``X`` is 0 until the project is ready for production.
``Y`` is the minor version.
``Z`` is the micro version.

Pre-release
^^^^^^^^^^^

Pre-releases are made as part of ClusterHQ's internal release process.
We don't currently solicit external feedback on pre-releases.

Pre-releases will have the version number of the next release with a ``rcX`` suffix, where ``X`` starts at ``1`` and is incremented for each pre-release.

There is a feature-freeze at the time that first pre-release for a given release is made.
The eventual final release is made from the last pre-release, including only bug fixes discovered during testing of the pre-release.

There must be at least one pre-release which will be tested for one week before the final release (a Major Marketing Release or Minor Marketing Release) is made.

Major Marketing Release
^^^^^^^^^^^^^^^^^^^^^^^

The content of major marketing releases will typically be planned significantly in advance
and will have a significant collection of new functionality.

Major marketing releases will be planned and scheduled by ClusterHQ's product team, in consultation with the marketing and engineering teams.

These releases must be preceded by at least one pre-release which will be tested for one week before the final release is made.

The version of a major marketing release will have the minor version number incremented from the previous marketing release, the micro version reset to 0.

Minor Marketing Release
^^^^^^^^^^^^^^^^^^^^^^^

Minor marketing releases will be made when some particular feature of a major marketing release is ready
and ClusterHQ's marketing team wants to announce that feature.
These release will typically be made in preparation for a blog post or other announcement of a feature.

Minor marketing releases will be planned and scheduled by ClusterHQ's product team, in consultation with the marketing and engineering teams.

These releases must be preceded by at least one pre-release which will be tested for one week before the final release is made.

The version of a minor marketing release will have the micro version number incremented from the previous marketing release.

Documentation Release
^^^^^^^^^^^^^^^^^^^^^

Documentation releases will be made when documentation for a major or minor marketing release is to be updated, without doing a full release.

Documentation releases will be planned and scheduled by ClusterHQ's product team, in consultation with the marketing and engineering teams.

The version of a documentation will have the version of the corresponding marketing release, with a ``.postX`` release, where ``X`` starts at ``1`` and is incremented for each documentation release.


Weekly Development Release
^^^^^^^^^^^^^^^^^^^^^^^^^^

Weekly releases are made primarily to facilitate the testing and automation of the release process itself.

If the previous release was a marketing release (either major or minor), the version of the following weekly release will increment the micro version
and append a ``.dev1`` suffix.
Otherwise, if the previous release was a weekly development release, the ``.devX`` suffix will be incremented.

Examples
^^^^^^^^

For example:

+-----------------+-------------------------------------------------+
| ``0.3.0``       | 0.3.0 released                                  |
+-----------------+-------------------------------------------------+
| ``0.3.1.dev1``  | Weekly releases of 0.3.1                        |
+-----------------+-------------------------------------------------+
| ``0.3.1``       | Micro marketing release                         |
+-----------------+-------------------------------------------------+
| ``0.3.1.post1`` | Documentation release of 0.3.1                  |
+-----------------+-------------------------------------------------+
| ``0.3.2.dev1``  | Weekly release                                  |
+-----------------+-------------------------------------------------+
| ``0.3.2.dev2``  | Weekly release                                  |
+-----------------+-------------------------------------------------+
| ``0.4.0rc1``    | Pre-release of 0.4.0                            |
+-----------------+-------------------------------------------------+
| ``0.4.0``       | Major marketing release                         |
+-----------------+-------------------------------------------------+

Production Releases
^^^^^^^^^^^^^^^^^^^

We intend to release version 1.0 when some set of features is determined to be production ready.
Our current intention is to adopt `semantic versioning`_ at that time, with regards to production ready features.

.. _`semantic versioning`: http://semver.org/


.. _`bugfix-releases`:

Bugfix Releases
^^^^^^^^^^^^^^^

ClusterHQ will not be producing bugfix releases until the project is ready for production.
