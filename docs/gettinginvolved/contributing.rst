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


Testing Code on Nodes
=====================


CentOS 7
^^^^^^^^

Start with some nodes which are configured correctly for Flocker.
A simple way to do this is to run the :ref:`acceptance test runner <acceptance-testing>` with the ``--keep`` option.

Log in to each node in the cluster, forwarding the authentication agent connection:

.. prompt:: bash alice@mercury$

   ssh -A root@${NODE_IP}

At this point it is possible to install packages built by `Buildbot`_.
This would be a more complete testing of code on a node.
However, it takes some time for packages to be built, and for development purposes the trade-off of a fast development cycle may be worthwhile.
Those trade-offs include the ability to test new or changed Python dependencies.
The following instructions replace just some of the code used by Flocker, but enough that can be useful.

On each node, run the following commands.
There are tools which allow you to run commands in multiple consoles simultaneously,
such as ``iTerm2`` for Mac OS X:

#. Install ``git``:

   .. prompt:: bash [root@node1]$

      sudo yum install -y git

#. Clone Flocker somewhere to use later:

   .. prompt:: bash [root@node1]$

      mkdir /flocker-source
      cd /flocker-source
      git clone git@github.com:ClusterHQ/flocker.git

#. Change the Flocker code in the checkout to what needs to be tested:

   .. prompt:: bash [root@node1]$

      cd /flocker-source/flocker
      git checkout BRANCH-NAME

#. Make a backup of the code and unit files which will be replaced:

   .. prompt:: bash [root@node1]$

      mkdir /backup
      cp -r /opt/flocker/lib/python2.7/site-packages/flocker/ /backup
      cp -r /etc/systemd/system/multi-user.target.wants/ /backup

#. Replace the node services with the new code:

   .. prompt:: bash [root@node1]$

      # Move Python code from the Git clone to where they are used
      rm -rf /opt/flocker/lib/python2.7/site-packages/flocker/
      cp -r /flocker-source/flocker/flocker/ /opt/flocker/lib/python2.7/site-packages/

      SYSTEMD_SOURCE_DIR=/flocker-source/flocker/admin/package-files/systemd/
      SOURCE_SERVICE_FILES=$(
         ls ${SYSTEMD_SOURCE_DIR}/*.service |
         xargs -n 1 -I {} sh -c 'basename {} .service'
      );

      # Stop systemd units before they are changed
      for service in ${SOURCE_SERVICE_FILES};
      do
         systemctl stop ${service}
      done

      # Move systemd unit files from the clone to where systemd will look for them
      # This uses /bin/cp instead of cp because sometimes cp is aliased to cp -i
      # which requires confirmation
      # This overwrites existing files (-f)
      /bin/cp -f ${SYSTEMD_SOURCE_DIR}/* /etc/systemd/system/multi-user.target.wants

      # Reload systemd, so that it can find new or changed units:
      systemctl daemon-reload

      # Start systemd units
      for service in ${SOURCE_SERVICE_FILES};
      do
         if [ "$(systemctl is-enabled ${service})" == 'enabled' ]
         then
           systemctl start ${service}
         fi
      done

   The services will take a short amount of time to start.
   Then the new code should be running on the node.

From then on, change the files in :file:`/flocker-source/flocker` (perhaps using ``git pull`` on each node) and run the above commands to replace the node services with the new code.
