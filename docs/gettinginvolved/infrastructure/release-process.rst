.. _release-process:

Release Process
===============

.. note::

   Make sure to follow the `latest documentation`_ when doing a release.

.. _latest documentation: http://doc-dev.clusterhq.com/gettinginvolved/infrastructure/release-process.html


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

- A web browser,
- `Vagrant`_ (1.6.2 or newer),
- `VirtualBox`_,
- ``vagrant-scp`` plugin:

  .. prompt:: bash $

     vagrant plugin install vagrant-scp

.. _`Vagrant`: https://docs.vagrantup.com/v2/
.. _`VirtualBox`: https://www.virtualbox.org/

Access
~~~~~~

- Access to Amazon `S3`_ with an `Access Key ID and Secret Access Key <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html>`_.
  It is possible that you will have an account but not the permissions to create an Access Key ID and Secret Access Key.

- SSH access to ClusterHQ's GitHub repositories.

- The ability to create issues in `the ClusterHQ JIRA <https://clusterhq.atlassian.net/secure/Dashboard.jspa>`_.

.. _preparing-for-a-release:

Preparing For a Release
-----------------------

#. Confirm that the release and the proposed version number have been approved.

   The release must have been approved, unless it is a weekly development release.
   Refer to the ClusterHQ `Flocker Releases and Versioning <https://docs.google.com/a/clusterhq.com/document/d/1xYbcU6chShgQQtqjFPcU1rXzDbi6ZsIg1n0DZpw6FfQ>`_ policy document.

   The version number must adhere to :ref:`the Flocker version numbering policy <version-numbers>`.

#. Export the version number of the release being created as an environment variable for later use:

   .. prompt:: bash $

      export VERSION=0.1.2

#. Create an issue in JIRA:

   This should be an "Improvement" in the current sprint, with "Release Flocker $VERSION" as the title, and it should be assigned to yourself.
   The issue does not need a design, so move the issue to the "Coding" state.

#. Create and log in to a new :doc:`Flocker development machine <vagrant>`:

   This uses SSH agent forwarding so that you can push changes to GitHub using the keys from your workstation.

   Add your SSH key to the ``sshd`` agent.
   Note that the ssh key you use must be linked to your GitHub account.

   .. prompt:: bash $

      [ -e "${SSH_AUTH_SOCK}" ] || eval $(ssh-agent)
      ssh-add $HOME/.ssh/id_rsa

   This copies your local git configuration from ``~/.gitconfig``.
   If this does not exist, commits made for the release will be associated with the default Vagrant username and email address.

   This copies your local configuration for `S3`_ from ``~/.aws``.
   If this does not exist, a later step will create it.

   .. prompt:: bash $

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      cd flocker-${VERSION}
      vagrant up
      vagrant scp default:/home/vagrant/.bashrc vagrant_bashrc
      echo export VERSION=${VERSION} >> vagrant_bashrc
      vagrant scp vagrant_bashrc /home/vagrant/.bashrc
      if [ -d ~/.aws ]; then vagrant scp "~/.aws" /home/vagrant; fi
      vagrant ssh -- -A

#. Create a release branch, and create and activate a virtual environment:

   .. prompt:: bash [vagrant@localhost]$

      # The following command means that you will not be asked whether
      # you want to continue connecting
      ssh-keyscan github.com >> ~/.ssh/known_hosts
      git clone git@github.com:ClusterHQ/flocker.git
      cd flocker
      mkvirtualenv flocker-release
      pip install --editable .[dev]
      admin/create-release-branch --flocker-version="${VERSION}"

#. Ensure the release notes in :file:`NEWS` are up-to-date:

   XXX: Process to be decided, see :issue:`523`.

   - The NEWS date format is YYYY-MM-DD.
   - The NEWS file should also be updated for each pre-release and Weekly Development Release, however there should be only one NEWS entry for each Major Marketing Release and Minor Marketing Release.
     This means that in doing a release, you may have to remove the previous development release or pre-release header, merging the changes from that previous release into the current release.

   .. note:: ``git log`` can be used to see all merges between two versions.

      .. prompt:: bash [vagrant@localhost]$

          # Choose the tag of the last version with a "NEWS" entry to compare the latest version to.
          export OLD_VERSION=0.3.0
          git log --first-parent ${OLD_VERSION}..release/flocker-${VERSION}

   .. prompt:: bash [vagrant@localhost]$

      git commit -am "Updated NEWS"

#. Ensure the notes in `docs/releasenotes/index.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/releasenotes/index.rst>`_ are up-to-date:

   - Update the "Release Notes" document.
   - (optional) Add a version heading.
     If this is a Major or Minor Marketing (pre-)release, the "Release Notes" document should have a heading corresponding to the release version.
     If this is a weekly development release, add a "Next Release" heading instead.
   - Refer to the appropriate internal release planning document on Google Drive for a list of features that were scheduled for this release, e.g. Product > Releases > Release 0.3.1, and add bullet points for those features that have been completed.
   - Add bullet points for any other *important* new features and improvements from the NEWS file above,
   - and add links (where appropriate) to documentation that has been added for those features.

   Finally, commit the changes:

   .. prompt:: bash [vagrant@localhost]$

      git commit -am "Updated Release Notes"

#. Ensure copyright dates in :file:`LICENSE` are up-to-date:

   - The list of years near the end of :file:`LICENSE` should include each year in which commits were made to the project.
   - This is already the case up to and including 2015.
   - If any such years are not present in the list, add them and commit the changes:

   .. prompt:: bash [vagrant@localhost]$

      git commit -am "Updated copyright"

#. Push the changes:

   .. prompt:: bash [vagrant@localhost]$

      git config push.default current
      git push

#. Ensure all the required tests pass on BuildBot:

   Pushing the branch in the previous step should have started a build on BuildBot.

   Unfortunately it is acceptable or expected for some tests to fail.
   Discuss with the team whether the release can continue given any failed tests.
   Some Buildbot builders may have to be run again if temporary issues with external dependencies have caused failures.

   In addition, review the link-check step of the documentation builder to ensure that all the errors (the links with "[broken]") are expected.

   XXX This should be explicit in Buildbot, see :issue:`1700`.

   At least the following builders do not have to pass in order to continue with the release process:

   - ``flocker-vagrant-dev-box``
   - Any ``docker-head`` builders.
   - Any builders in the "Expected failures" section.

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

   Make sure to follow the latest version of this documentation when reviewing a release.

#. Check the changes in the Pull Request:

   * The NEWS file has suitable changes.
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

#. The following steps should be done in the :doc:`Flocker development machine <vagrant>` created in :ref:`preparing-for-a-release`.
   If this is not running, start it again from the cloned Flocker repository created in :ref:`preparing-for-a-release`:

   .. prompt:: bash $

      vagrant up
      vagrant ssh -- -A

#. Tag the version being released:

   .. prompt:: bash [vagrant@localhost]$

      cd flocker
      workon flocker-release
      git tag --annotate "${VERSION}" "release/flocker-${VERSION}" -m "Tag version ${VERSION}"
      git push origin "${VERSION}"

#. Go to the `BuildBot web status <http://build.clusterhq.com/boxes-flocker>`_ and force a build on the tag.

   Force a build on a tag by putting the tag name (e.g. ``0.2.0``) into the branch box (without any prefix).

   .. note:: We force a build on the tag as well as the branch because the packages built before pushing the tag won't have the right version.
             Also, the package upload script currently expects the packages to be built from the tag, rather than the branch.

   Wait for the build to complete successfully.

#. Set up ``AWS Access Key ID`` and ``AWS Secret Access Key`` Amazon S3 credentials:

   Creating the Vagrant machine attempts to copy the ``~/.aws`` configuration directory from the host machine.
   This means that ``awscli`` may have correct defaults.

   .. prompt:: bash [vagrant@localhost]$

      aws configure

#. Publish artifacts and documentation:

   .. prompt:: bash [vagrant@localhost]$

      admin/publish-artifacts
      admin/publish-docs --production

#. Check that the documentation is set up correctly:

   The following command outputs error messages if the documentation does not redirect correctly.
   It outputs a success message if the documentation does redirect correctly.
   It can take some time for `CloudFront`_ invalidations to propagate, so retry this command for up to one hour if the documentation does not redirect correctly.

   .. prompt:: bash [vagrant@localhost]$

      admin/test-redirects --production

#. (Optional) Copy the AWS configuration to your local home directory:

   If the AWS configuration is on your workstation it will not have to be recreated next time you do a release.

   .. prompt:: bash [vagrant@localhost]$,$ auto

      [vagrant@localhost]$ logout
      Connection to 127.0.0.1 closed.
      $ vagrant scp default:/home/vagrant/.aws ~/

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
