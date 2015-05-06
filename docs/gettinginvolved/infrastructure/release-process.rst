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
- Fedora 20 RPMs for software on the node and client,
- CentOS 7 RPMs for software on the node and client,
- Ubuntu 14.04 DEBs for software on the node and client,
- a Vagrant base tutorial image,
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com>`_, and
- an updated Homebrew recipe.

For a maintenance or documentation release, we will have:

- a tag in version control,
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com>`_.


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

.. _`Vagrant`: https://docs.vagrantup.com/
.. _`VirtualBox`: https://www.virtualbox.org/

Access
~~~~~~

- Access to `Google Cloud Storage`_.

- Access to Amazon `S3`_ with an `Access Key ID and Secret Access Key <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html>`_.
  It is possible that you will have an account but not the permissions to create an Access Key ID and Secret Access Key.

- A member of a `ClusterHQ team on Atlas <https://atlas.hashicorp.com/settings/organizations/clusterhq/teams/>`_.

- SSH access to ClusterHQ's GitHub repositories.

.. note:: For a maintenance or documentation release, access to Google Cloud Storage and Atlas is not required.

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

   This copies your local git configuration from ``~/.gitconfig``.
   If this does not exist, commits made for the release will be associated with the default Vagrant username and email address.

   This copies your local configuration for `gsutil`_ and `S3`_ from ``~/.boto``.
   If this does not exist, a later step will create it.

   .. prompt:: bash $

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      cd flocker-${VERSION}
      vagrant up
      vagrant ssh -c "echo export VERSION=${VERSION} >> .bashrc"
      if [ -f ~/.boto ]; then vagrant scp "~/.boto" /home/vagrant; fi
      vagrant ssh -- -A

#. Create a release branch, and create and activate a virtual environment:

   .. prompt:: bash [vagrant@localhost]$

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      cd flocker-${VERSION}
      mkvirtualenv flocker-release-${VERSION}
      pip install --editable .[release]
      admin/create-release-branch --flocker-version="${VERSION}"
      git push --set-upstream origin release/flocker-${VERSION}

#. Ensure the release notes in :file:`NEWS` are up-to-date:

   XXX: Process to be decided, see :issue:`523`.

   - The NEWS date format is YYYY-MM-DD.
   - The NEWS file should also be updated for each pre-release and Weekly Development Release, however there should be only one NEWS entry for each Major Marketing Release and Minor Marketing Release.
   - This means that in doing a release, you may have to change the NEWS heading from a previous Weekly Development Release or pre-release.

   .. note:: ``git log`` can be used to see all merges between two versions.

      .. prompt:: bash [vagrant@localhost]$

          # Choose the tag of the last version with a "What's New" entry to compare the latest version to.
          export OLD_VERSION=0.3.0
          git log --first-parent ${OLD_VERSION}..release/flocker-${VERSION}

   .. prompt:: bash [vagrant@localhost]$

      git commit -am "Updated NEWS"

#. Ensure the notes in `docs/advanced/whatsnew.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/advanced/whatsnew.rst>`_ are up-to-date:

   - Update the "What's New" document.
   - (optional) Add a version heading.
     If this is a Major or Minor Marketing (pre-)release, the "What's New" document should have a heading corresponding to the release version.
     If this is a weekly development release, add a "Next Release" heading instead.
   - Refer to the appropriate internal release planning document for a list of features that were scheduled for this release, e.g. Product Development > Releases > Release 0.3.1, and add bullet points for those features that have been completed.
   - Add bullet points for any other *important* new features and improvements from the NEWS file above,
   - and add links (where appropriate) to documentation that has been added for those features.

   Finally, commit the changes:

   .. prompt:: bash [vagrant@localhost]$

      git commit -am "Updated What's New"

#. Ensure copyright dates in :file:`LICENSE` are up-to-date:

   - The list of years near the end of :file:`LICENSE` should include each year in which commits were made to the project.
   - This is already the case up to and including 2015.
   - If any such years are not present in the list, add them and commit the changes:

   .. prompt:: bash [vagrant@localhost]$

      git commit -am "Updated copyright"

#. Push the changes:

   .. prompt:: bash [vagrant@localhost]$

      git push

#. Ensure all the required tests pass on BuildBot:

   Go to the `BuildBot web status`_ and force a build on the just-created branch.

   The next steps in this section can be done while waiting for BuildBot to run, unless otherwise stated.

   Unfortunately it is acceptable or expected for some tests to fail.
   Discuss with the team whether the release can continue given any failed tests.
   Some Buildbot builders may have to be run again if temporary issues with external dependencies have caused failures.

   In addition, review the link-check step of the documentation builder to ensure that all the errors (the links with "[broken]") are expected.

   XXX This should be explicit in Buildbot, see :issue:`1700`.

   At least the following builders do not have to pass in order to continue with the release process:

   - ``flocker-vagrant-dev-box``
   - Any ``docker-head`` builders.
   - Any builders in the "Expected failures" section.

#. Update the Getting Started Guide ``Vagrantfile`` in a new branch:

   XXX This process should be changed, see :issue:`1307`.

   Change ``config.vm.box_version`` in the ``Vagrantfile`` to the version being released, in a new branch of the ``vagrant-flocker`` repository:

   .. prompt:: bash [vagrant@localhost]$

      cd
      git clone git@github.com:ClusterHQ/vagrant-flocker.git
      cd vagrant-flocker
      git checkout -b release/flocker-${VERSION} origin/master
      vi Vagrantfile

   Commit the changes and push the branch:

   .. prompt:: bash [vagrant@localhost]$

      git commit -am "Updated Vagrantfile"
      git push --set-upstream origin release/flocker-${VERSION}

#. Set up Google Cloud Storage and Amazon S3 credentials:

   Creating the Vagrant machine attempts to copy the ``~/.boto`` configuration file from the host machine.

   Run:

   .. prompt:: bash [vagrant@localhost]$

     gsutil ls gs:// s3://

   If the credentials have been set up correctly, you should see ClusterHQ's ``gs://`` and ``s3://`` buckets.
   If they have not, run:

   .. prompt:: bash [vagrant@localhost]$

      gsutil config

   and set ``aws_access_key_id`` and ``aws_secret_access_key`` in the ``[Credentials]`` section of ``~/.boto`` to allow access to Amazon `S3`_ using `gsutil`_.

#. Update the staging documentation:

   This requires the BuildBot step to have finished.

   .. prompt:: bash [vagrant@localhost]$

      ~/flocker-${VERSION}/admin/publish-docs --doc-version ${VERSION}

#. Make a pull request on GitHub:

   This requires the BuildBot step to have finished.

   The pull request should be for the release branch against ``master``, with a ``[FLOC-123]`` summary prefix, referring to the release issue that it resolves.
   Add a note to the pull request why any failed tests were deemed acceptable.

   Wait for an accepted code review before continuing.

   .. warning:: Add a note to the pull request description explaining that the branch should not be merged until the release process is complete.


.. _pre-tag-review:

Pre-tag Review Process
----------------------

A tag cannot be deleted once it has been pushed to GitHub (this is a policy and not a technical limitation).
So it is important to check that the code in the release branch is working before it is tagged.

.. note::

   Make sure to follow the latest version of this documentation when reviewing a release.

#. Check that the staging documentation is set up correctly:

   It takes some time for CloudFront invalidations to propagate and so wait up to one hour to try again if the documentation does not redirect correctly.
   To avoid some potential caching issues, try a solution like `BrowserStack`_ if the documentation does not redirect correctly after some time.

   XXX This should be automated, see :issue:`1701`.

   In the following URLs, treat ${VERSION} as meaning the version number of the release being reviewed.

   - The documentation should be available at https://docs.staging.clusterhq.com/en/${VERSION}/.

   - For a marketing release, the following URLs should redirect to the above URL.

     - https://docs.staging.clusterhq.com/
     - https://docs.staging.clusterhq.com/en/
     - https://docs.staging.clusterhq.com/en/latest/

     In addition, check that deep-links to `/en/latest/` work.
     https://docs.staging.clusterhq.com/en/latest/authors.html
     should redirect to
     ``https://docs.staging.clusterhq.com/en/${VERSION}/authors.html``

   - For a development release, the following redirects should work.

     - https://docs.staging.clusterhq.com/en/devel/ should redirect to ``https://docs.staging.clusterhq.com/en/${VERSION}/``
     - https://docs.staging.clusterhq.com/en/devel/authors.html should redirect to ``https://docs.staging.clusterhq.com/en/${VERSION}/authors.html``

#. Check the changes in the Pull Request:

   The "Files changed" should include changes to NEWS and What's New.
   For some releases it may include bug fixes or documentation changes which have been merged into the branch from which the release was created.
   These fixes or documentation changes may have to be merged into ``master`` in order to merge the release branch into ``master``.
   This should either block the acceptance of the release branch, or the team should discuss a workaround for that particular situation.

#. Update GitHub:

   If there are no problems spotted, comment on the Pull Request that the release engineer can continue by following :ref:`the Release section <release>` (do not merge the pull request).
   Otherwise, add comments to the Pull Request for any problems, and comment that they must be resolved before repeating this review process.

#.  Reject the JIRA issue.

    This is necessary because the release branch will need another review.

.. _release:

Release
-------

#. If it is not running in to the :doc:`Flocker development machine <vagrant>` created in :ref:`preparing-for-a-release`:

   From the cloned Flocker repository created in :ref:`preparing-for-a-release`:

   .. prompt:: bash $

      vagrant up
      vagrant ssh -- -A

#. Tag the version being released:

   .. prompt:: bash [vagrant@localhost]$

      cd flocker-${VERSION}
      workon flocker-release-${VERSION}
      git tag --annotate "${VERSION}" "release/flocker-${VERSION}" -m "Tag version ${VERSION}"
      git push origin "${VERSION}"

#. Go to the `BuildBot web status`_ and force a build on the tag.

   Force a build on a tag by putting the tag name (e.g. ``0.2.0``) into the branch box (without any prefix).

   .. note:: We force a build on the tag as well as the branch because the RPMs built before pushing the tag won't have the right version.
             Also, the RPM upload script currently expects the RPMs to be built from the tag, rather than the branch.

   Wait for the build to complete successfully.

#. Build and upload artifacts:

   .. note:: Skip this step for a maintenance or documentation release.

   .. prompt:: bash [vagrant@localhost]$

      # Build Python and RPM packages and upload them to Amazon S3
      admin/publish-artifacts
      # Copy the tutorial box to the final location
      gsutil cp -a public-read gs://clusterhq-vagrant-buildbot/tutorial/flocker-tutorial-${VERSION}.box gs://clusterhq-vagrant/flocker-tutorial-${VERSION}.box

#. Add the tutorial box to Atlas:

   .. note:: Skip this step for a maintenance or documentation release.

   XXX This should be automated, see :issue:`943`.

   .. prompt:: bash [vagrant@localhost]$

      echo https://storage.googleapis.com/clusterhq-vagrant/flocker-tutorial-${VERSION}.box

   Use the echoed URL as the public link to the Vagrant box, and perform the steps to :ref:`add-vagrant-box-to-atlas`.

#. Test the Getting Started Guide:

   XXX This process should be changed, see :issue:`1307`.

   XXX This process should be automated, see :issue:`1309`.

   .. note:: This cannot be done from within the  :doc:`Flocker development machine <vagrant>` (but keep that open for later steps).

   Run through the Getting Started guide from the documentation built for the tag on any one client platform, with Vagrant as the node platform, with one change:
   after cloning ``vagrant-flocker`` in the Installation > Vagrant section, check out the new branch:

   XXX This process should be automated, see :issue:`1309`.

   .. prompt:: bash $

      git checkout release/flocker-${VERSION}

   Test the client install instructions work on all supported platforms by following the instructions and checking the version:

   .. prompt:: bash $

      flocker-deploy --version

   The expected version is the version being released.

#. Update the documentation.

   This should be done from the :doc:`Flocker development machine <vagrant>`.

   If this machine is no longer connected to, go to the clone of ``flocker-${VERSION}`` and SSH into the machine:

   .. prompt:: bash $

      vagrant up
      vagrant ssh -- -A

   .. prompt:: bash [vagrant@localhost]$

      cd ~/flocker-${VERSION}
      workon flocker-release-${VERSION}
      admin/publish-docs --production

#. If the release is a marketing release, merge the new ``vagrant-flocker`` branch.

   .. warning:: It takes some time for CloudFront invalidations to propagate.
      This means that there will be a short period for some users where the documentation will still be for the previous version but the ``Vagrantfile`` downloads the latest tutorial box.

   .. prompt:: bash [vagrant@localhost]$

      cd ~/vagrant-flocker
      git checkout master
      git merge origin/release/flocker-${VERSION}
      git push

#. Copy the ``boto`` configuration file to your local home directory:

   If the ``boto`` configuration is on your workstation it will not have to be recreated next time you do a release.

   .. prompt:: bash [vagrant@localhost]$,$ auto

      [vagrant@localhost]$ logout
      Connection to 127.0.0.1 closed.
      $ vagrant scp default:/home/vagrant/.boto ~/

#. Submit the release pull request for review again.

Post-Release Review Process
---------------------------

#. Check that the documentation is set up correctly:

   It takes some time for CloudFront invalidations to propagate and so wait up to one hour to try again if the documentation does not redirect correctly.
   To avoid some potential caching issues, try a solution like `BrowserStack`_ if the documentation does not redirect correctly after some time.

   XXX This should be automated, see :issue:`1701`.

   In the following URLs, treat ${VERSION} as meaning the version number of the release being reviewed.

   - The documentation should be available at https://docs.clusterhq.com/en/${VERSION}/.

   - For a marketing release, the following URLs should redirect to the above URL.

     - https://docs.clusterhq.com/
     - https://docs.clusterhq.com/en/
     - https://docs.clusterhq.com/en/latest/

     In addition, check that deep-links to `/en/latest/` work.
     https://docs.clusterhq.com/en/latest/authors.html
     should redirect to
     ``https://docs.clusterhq.com/en/${VERSION}/authors.html``

   - For a development release, the following redirects should work.

     - https://docs.clusterhq.com/en/devel/ should redirect to ``https://docs.clusterhq.com/en/${VERSION}/``
     - https://docs.clusterhq.com/en/devel/authors.html should redirect to ``https://docs.clusterhq.com/en/${VERSION}/authors.html``

#. Verify that the client (``flocker-deploy``) can be installed on all supported platforms:

   Follow the Flocker client installation documentation at ``https://docs.clusterhq.com/en/${VERSION}/indepth/installation.html#installing-flocker-cli``.

   XXX: This step should be documented, see :issue:`1622`.

   XXX: This step should be automated, see :issue:`1039`.

#. Merge the release pull request.
   Do not delete the release branch because it may be used as a base branch for future releases.


Improving the Release Process
-----------------------------

The release engineer should aim to spend up to one day improving the release process in whichever way they find most appropriate.
If there is no existing issue for the planned improvements then a new one should be made.
Look at `existing issues relating to the release process <https://clusterhq.atlassian.net/issues/?jql=labels%20%3D%20release_process%20AND%20status%20!%3D%20done>`_.
The issue(s) for the planned improvements should be put into the next sprint.


.. _gsutil: https://developers.google.com/storage/docs/gsutil
.. _wheel: https://pypi.python.org/pypi/wheel
.. _Google cloud storage: https://console.developers.google.com/project/apps~hybridcluster-docker/storage/archive.clusterhq.com/
.. _BuildBot web status: http://build.clusterhq.com/boxes-flocker
.. _virtualenv: https://pypi.python.org/pypi/virtualenv
.. _Homebrew: http://brew.sh
.. _CloudFront: https://console.aws.amazon.com/cloudfront/home
.. _S3: https://console.aws.amazon.com/s3/home
.. _BrowserStack: https://www.browserstack.com/
