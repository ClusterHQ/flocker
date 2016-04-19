.. _release-process:

===============
Release Process
===============

.. note::

   Make sure to follow the `latest documentation <http://clusterhq-staging-docs.s3.amazonaws.com/master/gettinginvolved/infrastructure/release-process.html>`_ when doing a release.

Outcomes
========

By the end of the release process we will have:

- a tag in version control,
- a Python wheel on Amazon `S3`_,
- CentOS 7 RPMs for software on the node and client,
- Ubuntu 14.04 DEBs for software on the node and client,
- Ubuntu 15.10 DEBs for software on the node and client,
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com/>`_, and

For a maintenance or documentation release, we will have:

- a tag in version control,
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com/>`_.


Prerequisites
=============

Software
--------

**All Platforms**

* `Docker <https://docs.docker.com/installation/>`_
* `virtualenvwrapper <https://virtualenvwrapper.readthedocs.org/en/latest/install.html>`_
* `Packer <https://www.packer.io>`_
   The Packer command must be installed at ``/opt/packer/packer``.

**OS X**

* `Homebrew <http://brew.sh>`_

.. prompt:: bash $

   brew tap stepanstipl/noop
   brew install createrepo dpkg

**Ubuntu**

.. prompt:: bash $

   sudo apt-get update
   sudo apt-get install -y dpkg-dev createrepo

**Fedora**

.. prompt:: bash $

   sudo yum install -y dpkg-dev createrepo

Access
------

* Access to Amazon `S3`_ with an `Access Key ID and Secret Access Key <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html>`_.
  It is possible that you will have an account but not the permissions to create an Access Key ID and Secret Access Key.

* SSH access to ClusterHQ's GitHub repositories.

* The ability to create issues in `the ClusterHQ JIRA <https://clusterhq.atlassian.net/secure/Dashboard.jspa>`_.

* The ability to force builds on ClusterHQ's BuildBot and Jenkins.
  This requires an administrator password which can be found in ClusterHQ's LastPass.

* Access to ClusterHQ's Google Drive for access to ClusterHQ versioning policy documents.

.. _preparing-for-a-release:

Preparing For a Release
=======================

#. Confirm that the release and the proposed version number have been approved.

   The release must have been approved, unless it is a weekly development release.
   Refer to the ClusterHQ `Flocker Releases and Versioning <https://docs.google.com/a/clusterhq.com/document/d/1xYbcU6chShgQQtqjFPcU1rXzDbi6ZsIg1n0DZpw6FfQ>`_ policy document.

   The version number must adhere to :ref:`the Flocker version numbering policy <version-numbers>`.


#. Create an issue in JIRA:

   This should be a "Feature" with "Release Flocker [VERSION]" as the title, and it should be assigned to yourself.
   The issue does not need a design, so move the issue to the "Coding" state.

#. Create the release repository, environment and branch from within an existing Flocker development environment:

   .. prompt:: bash $

      admin/initialize-release --flocker-version=1.6.2

   Execute the commands output by the `initialize-release` script:

   .. prompt:: bash $

      export VERSION=1.6.2;
      cd /home/developer/flocker-release-1.6.2;
      source flocker-1.6.2/bin/activate;

#. Ensure the notes in `docs/releasenotes/index.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/releasenotes/index.rst>`_ are up-to-date:

   .. note:: ``git log`` can be used to see all merges between two versions.

      .. prompt:: bash (flocker-1.6.2)$

          # Choose the tag of the last version with a "Release Notes" entry to compare the latest version to.
          OLD_VERSION=1.6.1

          BRANCH=$(git rev-parse --abbrev-ref HEAD)
          git log --first-parent ${OLD_VERSION}..${BRANCH}

   - Update the "Release Notes" document.
   - (optional) Add a version heading.
     If this is a Major or Minor Marketing (pre-)release, the "Release Notes" document should have a heading corresponding to the release version.
     If this is a weekly development release, add a "Next Release" heading instead.
   - Refer to the appropriate internal release planning document on Google Drive for a list of features that were scheduled for this release, e.g. Product > Releases > Release 0.3.1, and add bullet points for those features that have been completed.
   - Add bullet points for any other *important* new features and improvements from the ``git log`` above,
   - and add links (where appropriate) to documentation that has been added for those features.

   Finally, commit the changes:

   .. prompt:: bash (flocker-1.6.2)$

      git commit -am "Updated Release Notes"

#. Push the changes:

   .. prompt:: bash (flocker-1.6.2)$

      git push --set-upstream origin $(git rev-parse --abbrev-ref HEAD)

#. Ensure all the required tests pass on Jenkins:

   To run the tests on `Jenkins`_, first run ``setup_ClusterHQ-flocker-release`` using the release branch as the parameter to the job.
   This will generate two sets of test jobs for the release branch which can be accessed from the `releases view <http://ci-live.clusterhq.com:8080/job/ClusterHQ-flocker/view/releases/>`_.
   For the following steps, use the results of the jobs within "Release release/flocker-<VERSION>" as these do not perform any pre-build merging with master.

   To run the tests, force a build of the ``__main_multijob`` job.
   Some of the tests will not be triggered by this (such as the acceptance tests), so these will also need to be started.

   Discuss with the team whether the release can continue given any failed tests outside of expected failures.
   Some jobs may have to be run again if temporary issues with external dependencies have caused failures.

   In addition, review the link-check step of the documentation builder to ensure that all the errors (the links with "[broken]") are expected.

#. Make a pull request on GitHub:

   The pull request should be for the release branch against ``master``, with a ``[FLOC-123]`` summary prefix, referring to the release issue that it resolves.
   Add a note to the pull request why any failed tests were deemed acceptable.

   Wait for an accepted code review before continuing.

.. _pre-tag-review:

Pre-tag Review Process
======================

A tag must not be deleted once it has been pushed to GitHub.
This is a policy and not a technical limitation, as removing tags can cause problems for anyone who has updated a cloned copy of the repository.

It is important to check that the code in the release branch is working before it is tagged.

.. note::

   Make sure to follow the `latest review process <http://doc-dev.clusterhq.com/gettinginvolved/infrastructure/release-process.html#pre-tag-review>`_ when reviewing a release.

#. Check the changes in the Pull Request:

   * The release notes at :file:`docs/releasenotes/index.rst` should be up to date.
   * The build should be passing to the team's satisfaction.
     See "Ensure all the required tests pass on Jenkins" in :ref:`preparing-for-a-release`.

   For some releases the Pull Request may include bug fixes or documentation changes which have been merged into the branch from which the release branch was created,
   for example a previous pre-release.
   These fixes can be ignored in this review.

#. Update GitHub and JIRA:

   If there were no problems spotted while checking the changes, comment on the Pull Request that the release engineer can continue by following :ref:`the Release section <release>`.
   Do not merge the Pull Request as this should happen after the branch has been tagged.
   Accept the JIRA issue, and add a comment that the release process can continue.

   If a problem was spotted, add comments to the Pull Request for each problem, and comment that they must be resolved before repeating this review process.
   Reject the JIRA issue and assign it to the release engineer.


.. _release:

Release
=======

.. note::

   The following commands must be run from within the virtualenv and directory created in :ref:`preparing-for-a-release`.

#. Tag the version being released:

   .. prompt:: bash (flocker-1.6.2)$

      BRANCH=$(git rev-parse --abbrev-ref HEAD)
      RELEASE_BRANCH_PREFIX="release\/flocker-"
      TAG=${BRANCH/${RELEASE_BRANCH_PREFIX}}
      git tag --annotate "${TAG}" "${BRANCH}" -m "Tag version ${TAG}"
      git push origin "${TAG}"

#. Go to `Jenkins`_ and force a build on the release branch to test the latest commit.

   Currently, jobs cannot be created for git tags so the latest commit must be tested instead.
   This must be the same commit as the tag.
   The git commit that was used can be seen on the summary page for any build.
   To test this commit, force a build of the ``__main_multijob`` job and any other jobs which are not triggered by this.

#. Go to the `BuildBot web status <http://build.clusterhq.com/boxes-flocker>`_ and force a build on the tag.

   Although the tests are run on Jenkins, we still use Buildbot to build the packages.

   Force a build on a tag by putting the tag name (e.g. ``0.2.0``) into the branch box (without any prefix).

   .. note::

      Although there would not have been any changes since the branch was built during the :ref:`preparing-for-a-release` process, we need to build on the tag as the packages that were built before pushing the tag won't have the right version.

   Wait for the build to complete successfully.

#. Set up ``AWS Access Key ID`` and ``AWS Secret Access Key`` Amazon S3 credentials:

   .. prompt:: bash (flocker-1.6.2)$

      aws configure

   Enter your access key and secret token when prompted.
   The other configurable values may be left as their defaults.

#. Update the CloudFormation installer template.

   .. _release-process-cloudformation:

   The following commands will generate new AWS AMI images with this version of Flocker pre-installed.
   The new AMI images will be used in the CloudFormation template used in the :ref:`docker-integration` installation instructions.

   .. code:: console

      FLOCKER_VERSION="${TAG:?}"

      DOCKER_VERSION=1.10.0
      SWARM_VERSION=1.1.0

      export FLOCKER_VERSION DOCKER_VERSION SWARM_VERSION

      admin/ami-search-ubuntu > /tmp/ami_map_ubuntu.json

      admin/publish-installer-images \
          --copy_to_all_regions \
          --template=docker \
          --source-ami-map="$(<ami_map_ubuntu.json)" > ami_map_docker.json

      admin/publish-installer-images \
          --copy_to_all_regions \
          --template=flocker \
          --source-ami-map="$(<ami_map_docker.json)" > ami_map_flocker.json

      admin/create-cloudformation-template \
           --client-ami-map-body="$(<ami_map_docker.json)" \
           --node-ami-map-body="$(<ami_map_flocker.json)" \
           > "flocker-cluster.cloudformation.${FLOCKER_VERSION}.json"

      aws --region us-east-1 \
          s3 cp --acl public-read \
          "flocker-cluster.cloudformation.${FLOCKER_VERSION}.json" \
          s3://installer.downloads.clusterhq.com/

#. Publish artifacts and documentation:

   .. prompt:: bash (flocker-1.6.2)$

      admin/publish-artifacts
      admin/publish-docs --production

#. Check that the artifacts are set up correctly:

   .. note:: Ensure that Docker is installed and running, and can be controlled from the current user account.
      Run ``docker ps`` to check for any problems.

   The following command tests that the client packages can be installed on a number of platforms.
   This helps to identify any problems with the published artifacts that may not be evident in the regular tests (e.g. S3 permissions or packaging problems).
   This test can take about 30 minutes, especially if Docker images need to be pulled.

   .. prompt:: bash (flocker-1.6.2)$

      admin/test-artifacts

   If an error occurs for any tests, create a JIRA issue and raise it with the team.
   In any case, continue with the release.

#. Remove the release virtual environment:

   .. prompt:: bash (flocker-1.6.2)$,$ auto

      (flocker-1.6.2)$ VIRTUALENV_NAME=$(basename ${VIRTUAL_ENV})
      (flocker-1.6.2)$ deactivate
      $ rmvirtualenv ${VIRTUALENV_NAME}

#. Remove the release Flocker clone:

   .. warning:: ``rm -rf`` can be dangerous, run this at your own risk.

   .. prompt:: bash $

      rm -rf ${PWD}

#. Merge the release branch into master:

   If there are no conflicts, merge the pull request.
   If there are conflicts; create a new branch, merge forward and create a pull-request of that branch against master.

   .. prompt:: bash $

      git checkout -b merge-release-${VERSION}-FLOC-XXX release/flocker-${VERSION}
      git pull origin master

   Merging this pull-request will also close the release pull request.
   The ``merge-release-*-FLOC-XXX`` branch should be deleted once the pull-request has been merged.

   Unless this is a development release,
   do not delete the release branch because it may be used as a base branch for future releases.


Improving the Release Process
=============================

The release engineer should aim to spend up to one day improving the release process in whichever way they find most appropriate.
If there is no existing issue for the planned improvements then a new one should be made.
Look at `existing issues relating to the release process <https://clusterhq.atlassian.net/issues/?jql=labels%20%3D%20release_process%20AND%20status%20!%3D%20done>`_.
The issue(s) for the planned improvements should be put into the next sprint.

.. _Jenkins: http://ci-live.clusterhq.com:8080/
.. _CloudFront: https://console.aws.amazon.com/cloudfront/home
.. _S3: https://console.aws.amazon.com/s3/home
