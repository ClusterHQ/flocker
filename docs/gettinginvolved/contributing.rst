.. include:: ../../CONTRIBUTING.rst

.. _maintenance-branches:

Maintenance Branches
====================

.. note::

   As :ref:`bugfix releases<bugfix-releases>` aren't currently being produced,
   the following instructions are only relevant for documentation fixes.


Occasionally, issues will be discovered that want to be fixed before the next full release.
The following is the procedure for fixing them.

#. File an issue in JIRA_.
   For example, "FLOC-1234: Fix a bug.".
   If the issue affects in multiple versions (including master),
   create a sub-task for each affected, supported version:

   - FLOC-1235: Fix a bug in 1.2.3.
   - FLOC-1236: Fix a bug in 1.2.4.
   - FLOC-1237: Fix a bug in master.

#. Create branch off the oldest affected, supported release.

   .. prompt:: bash $

      git checkout -b release-maintenance/flocker-1.2.3/fix-a-bug-FLOC-1235 origin/release/flocker-1.2.3

#. Fix the bug.

   .. prompt:: bash $

      ed ...
      git commit -m'Fixed the bug.'

#. Push the branch to GitHub.

   .. prompt:: bash $

      git push origin --set-upstream release-maintenance/flocker-1.2.3/fix-a-bug-FLOC-1235

#. Create a pull-request against the release branch.

   https://github.com/ClusterHQ/flocker/compare/release/flocker-1.2.3...release-maintenance/flocker-1.2.3/fix-a-bug-FLOC-1234?expand=1

   Note in the pull request that the branch shouldn't be deleted until every affected release and master have received the fix.
   Otherwise, commits are liable to be lost between branches.

#. Wait for the pull-request to be accepted.

#. For each other affected release, create a branch against that release, merge-forward, then create a pull-request.

   .. prompt:: bash $

      git checkout -b release-maintenance/flocker-1.2.4/fix-a-bug-FLOC-1236 origin/release-maintenance/flocker-1.2.3/fix-a-bug-FLOC-1235
      # The following command is only necesary if there are merge conflicts to resolve
      git merge origin/release/flocker-1.2.4
      git push origin --set-upstream release-maintenance/flocker-1.2.4/fix-a-bug-FLOC-1236

#. If master is affected, create a branch against master, merge-forward, then create a pull-request.

   .. prompt:: bash $

      git checkout -b fix-a-bug-FLOC-1236 origin/release-maintenance/flocker-1.2.3/fix-a-bug-FLOC-1235
      # The following command is only necesary if there are merge conflicts to resolve
      git merge origin/master
      git push origin --set-upstream fix-a-bug-FLOC-1236

#. Delete all the merged branches.


Pre-release Branches
====================

Similarly to `maintenance-branches`_, bug fixes and improvements may need to be applied to pre-releases.
These changes should be the only changes between pre-releases for the same marketing release, and the only changes between the last pre-release and the final marketing release.

Follow the procedure for merging fixes into maintenance branches, merging fixes into the last pre-release.
