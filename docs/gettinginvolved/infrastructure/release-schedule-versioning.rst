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
The release engineer should then spend 4-8 hours working on fixing issues related to improving the release process.
If there is an issue that will likely take over 8 hours then they should consult the team manager before starting them.

Version Numbers
---------------

Released version numbers take the form of ``X.Y.Z``.
The current value of ``X`` is 0 until the project is ready for production.

``Y`` is the "marketing version".
ClusterHQ's marketing department is made aware of the content of a release ahead of time.
If the marketing department decides that this release is sufficiently important to publicize then ``Y`` is incremented and ``Z`` is set to 0.

``Z`` is incremented for each standard weekly release.

Patch Releases
--------------

ClusterHQ will not be producing patch releases until the project is ready for production.
