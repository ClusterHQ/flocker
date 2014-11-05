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

1.0 Production Release
^^^^^^^^^^^^^^^^^^^^^^

We intend to release version 1.0 when some set of features is determined to be production ready.
Our current intention is to adopt `semantic versioning`_ at that time, with regards to production ready features.

.. _`semantic versioning`: http://semver.org/

Major Marketing Release
^^^^^^^^^^^^^^^^^^^^^^^
The content of a major marketing releases will typically planned significantly in advance
and will have a significant collection of new functionality.
The determination of when to make a major marketing release will be made by ClusterHQ's product team, in consultation with the marketing and engineering teams.

These releases will typically get thorough pre-release testing.

The version of a major marketing release will have the minor version number incremented from the previous marketing release, the micro version reset to 0.

Minor Marketing Release
^^^^^^^^^^^^^^^^^^^^^^^
Minor marketing releases will be made when some particular feature of a major marketing release is ready
and ClusterHQ's marketing team wants to announce that feature.
These release will typically be made in preparation for a blog post or other announcement of a feature.
The determination of when to make a minor marketing release will be made by ClusterHQ's product team, in consultation with the marketing and engineering teams.

The version of a minor marketing release will have the micro version number incremented from the previous marketing release.

Weekly Development Release
^^^^^^^^^^^^^^^^^^^^^^^^^^
Weekly releases are made primarily to facilitate the testing and automation of the release process itself.

If the previous release was a marketing release (either major or minor), the version of the following weekly release will increment the micro version
and append a ``dev1`` suffix.
Otherwise, if the previous release was a weekly development release, the ``devX`` suffix will be incremented.


Pre-release
^^^^^^^^^^^
Pre-releases are made as part of ClusterHQ's internal release process.
We don't currently solicit external feedback on pre-releases.

Pre-releases will have the version number of the next release with a ``preX`` suffix, where ``X`` starts at ``1`` and is incremented for each pre-release.

Examples
^^^^^^^^

For example:

+---------------+-------------------------------------------------+
| ``0.3.0``     | 0.3.0 released                                  |
+---------------+-------------------------------------------------+
| ``0.3.1dev1`` | Weekly releases of 0.3.1                        |
+---------------+-------------------------------------------------+
| ``0.3.1``     | Micro marketing release                         |
+---------------+-------------------------------------------------+
| ``0.3.2dev1`` | Weekly release                                  |
+---------------+-------------------------------------------------+
| ``0.3.2dev2`` | Weekly release                                  |
+---------------+-------------------------------------------------+
| ``0.4.0pre1`` | Pre-release of 0.4.0                            |
+---------------+-------------------------------------------------+
| ``0.4.0``     | 0.4.0 released                                  |
+---------------+-------------------------------------------------+

Bugfix Releases
^^^^^^^^^^^^^^^

ClusterHQ will not be producing bugfix releases until the project is ready for production.
