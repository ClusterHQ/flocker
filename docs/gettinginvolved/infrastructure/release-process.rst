.. _release-process:

Release Process
===============

.. note::

   Make sure to follow the :ref:`latest documentation <latest:release-process>` when doing a release.

Outcomes
--------

By the end of the release process we will have:

- a tag in version control,
- a Python wheel on Amazon `S3`_,
- CentOS 7 RPMs for software on the node and client,
- Ubuntu 14.04 DEBs for software on the node and client,
- Ubuntu 15.04 DEBs for software on the node and client,
- a Vagrant base tutorial image,
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com/>`_, and
- an updated Homebrew recipe.

For a maintenance or documentation release, we will have:

- a tag in version control,
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com/>`_.


Prerequisites
-------------

Software
~~~~~~~~

All Platforms
*************

`virtualenvwrapper <https://virtualenvwrapper.readthedocs.org/en/latest/install.html>`_

OS X
*****

`Homebrew <http://brew.sh>`_

.. prompt:: bash $

   brew tap stepanstipl/noop
   brew install createrepo dpkg

Ubuntu
******

.. prompt:: bash $

   sudo apt-get update
   sudo apt-get install -y dpkg-dev createrepo

Fedora
******

.. prompt:: bash $

   sudo yum install -y dpkg-dev createrepo


Access
~~~~~~

- Access to Amazon `S3`_ with an `Access Key ID and Secret Access Key <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html>`_.
  It is possible that you will have an account but not the permissions to create an Access Key ID and Secret Access Key.

- SSH access to ClusterHQ's GitHub repositories.

- The ability to create issues in `the ClusterHQ JIRA <https://clusterhq.atlassian.net/secure/Dashboard.jspa>`_.

- The ability to force builds on ClusterHQ's BuildBot.
  This requires an administrator password which can be found in ClusterHQ's LastPass.

- Access to ClusterHQ's Google Drive for access to ClusterHQ versioning policy documents.

.. _preparing-for-a-release:

Preparing For a Release
-----------------------

#. Confirm that the release and the proposed version number have been approved.

   The release must have been approved, unless it is a weekly development release.
   Refer to the ClusterHQ `Flocker Releases and Versioning <https://docs.google.com/a/clusterhq.com/document/d/1xYbcU6chShgQQtqjFPcU1rXzDbi6ZsIg1n0DZpw6FfQ>`_ policy document.

   The version number must adhere to :ref:`the Flocker version numbering policy <version-numbers>`.


#. Set the version number of the release being created as an environment variable for later use:

   .. prompt:: bash $

      VERSION=0.1.2

#. Create an issue in JIRA:

   This should be a "Feature" with "Release Flocker ${VERSION}" as the title, and it should be assigned to yourself.
   The issue does not need a design, so move the issue to the "Coding" state.

#. Create an environment to do a release in:

   .. prompt:: bash $,(flocker-0.1.2)$ auto

      $ git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      # Use system site packages e.g. so that "rpm" can be imported
      $ mkvirtualenv -a "flocker-${VERSION}" --system-site-packages "flocker-${VERSION}"
      (flocker-0.1.2)$ pip install --ignore-installed --editable .[dev]
      (flocker-0.1.2)$ admin/create-release-branch --flocker-version=${VERSION}
      (flocker-0.1.2)$ admin/update-license
      (flocker-0.1.2)$ git commit -am "Updated copyright in LICENSE file"

#. Ensure the notes in `docs/releasenotes/index.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/releasenotes/index.rst>`_ are up-to-date:

   .. note:: ``git log`` can be used to see all merges between two versions.

      .. prompt:: bash (flocker-0.1.2)$

          # Choose the tag of the last version with a "Release Notes" entry to compare the latest version to.
          OLD_VERSION=0.3.0

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

   .. prompt:: bash (flocker-0.1.2)$

      git commit -am "Updated Release Notes"

#. Push the changes:

   .. prompt:: bash (flocker-0.1.2)$

      git push --set-upstream origin $(git rev-parse --abbrev-ref HEAD)

#. Ensure all the required tests pass on BuildBot:

   Pushing the branch in the previous step should have started a build on BuildBot.
   If not, you can force a build by logging in to BuildBot, entering the release branch name in to the box at the top right and clicking the ``Force`` button.

   Discuss with the team whether the release can continue given any failed tests outside of expected failures.
   Some Buildbot builders may have to be run again if temporary issues with external dependencies have caused failures.

   In addition, review the link-check step of the documentation builder to ensure that all the errors (the links with "[broken]") are expected.

#. Make a pull request on GitHub:

   The pull request should be for the release branch against ``master``, with a ``[FLOC-123]`` summary prefix, referring to the release issue that it resolves.
   Add a note to the pull request why any failed tests were deemed acceptable.

   Wait for an accepted code review before continuing.

.. _pre-tag-review:

Pre-tag Review Process
----------------------

A tag must not be deleted once it has been pushed to GitHub (this is a policy and not a technical limitation).
So it is important to check that the code in the release branch is working before it is tagged.

.. note::

   Make sure to follow the :ref:`latest review process <latest:pre-tag-review>` when reviewing a release.

#. Check the changes in the Pull Request:

   * The release notes at :file:`docs/releasenotes/index.rst` should be up to date.
   * The build should be passing to the team's satisfaction.
     See "Ensure all the required tests pass on BuildBot" in :ref:`preparing-for-a-release`.

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
-------

.. note::

   The following commands must be run from within the virtualenv and directory created in :ref:`preparing-for-a-release`.

#. Tag the version being released:

   .. prompt:: bash (flocker-0.1.2)$

      BRANCH=$(git rev-parse --abbrev-ref HEAD)
      RELEASE_BRANCH_PREFIX="release\/flocker-"
      TAG=${BRANCH/${RELEASE_BRANCH_PREFIX}}
      git tag --annotate "${TAG}" "${BRANCH}" -m "Tag version ${TAG}"
      git push origin "${TAG}"

#. Go to the `BuildBot web status <http://build.clusterhq.com/boxes-flocker>`_ and force a build on the tag.

   Force a build on a tag by putting the tag name (e.g. ``0.2.0``) into the branch box (without any prefix).

   .. note:: We force a build on the tag as well as the branch because the packages built before pushing the tag won't have the right version.
             Also, the package upload script currently expects the packages to be built from the tag, rather than the branch.

   Wait for the build to complete successfully.

#. Set up ``AWS Access Key ID`` and ``AWS Secret Access Key`` Amazon S3 credentials:

   .. prompt:: bash (flocker-0.1.2)$

      aws configure

   Enter your access key and secret token when prompted.
   The other configurable values may be left as their defaults.

#. Publish artifacts and documentation:

   .. prompt:: bash (flocker-0.1.2)$

      admin/publish-artifacts
      admin/publish-docs --production

#. Check that the documentation is set up correctly:

   The following command outputs error messages if the documentation does not redirect correctly.
   It outputs a success message if the documentation does redirect correctly.
   It can take some time for `CloudFront`_ invalidations to propagate, so retry this command for up to one hour if the documentation does not redirect correctly.

   .. prompt:: bash (flocker-0.1.2)$

      admin/test-redirects --production

#. Remove the release virtual environment:

   .. prompt:: bash (flocker-0.1.2)$,$ auto

      (flocker-0.1.2)$ VIRTUALENV_NAME=$(basename ${VIRTUAL_ENV})
      (flocker-0.1.2)$ deactivate
      $ rmvirtualenv ${VIRTUALENV_NAME}

#. Remove the release Flocker clone:

   .. warning:: ``rm -rf`` can be dangerous, run this at your own risk.

   .. prompt:: bash $

      rm -rf ${PWD}

#. Merge the release pull request.
   Do not delete the release branch because it may be used as a base branch for future releases.


Improving the Release Process
-----------------------------

The release engineer should aim to spend up to one day improving the release process in whichever way they find most appropriate.
If there is no existing issue for the planned improvements then a new one should be made.
Look at `existing issues relating to the release process <https://clusterhq.atlassian.net/issues/?jql=labels%20%3D%20release_process%20AND%20status%20!%3D%20done>`_.
The issue(s) for the planned improvements should be put into the next sprint.

.. _CloudFront: https://console.aws.amazon.com/cloudfront/home
.. _S3: https://console.aws.amazon.com/s3/home
