Release Process
===============

.. note::

   Make sure to follow the `latest documentation`_ when doing a release.

.. _latest documentation: http://doc-dev.clusterhq.com/gettinginvolved/infrastructure/release-process.html


Outcomes
--------

By the end of the release process we will have:

- a tag in version control,
- a Python wheel in the `ClusterHQ package index <http://archive.clusterhq.com>`_,
- Fedora 20 RPMs for software on the node and client,
- a Vagrant base tutorial image,
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com>`_, and
- an updated Homebrew recipe.

For a documentation release, we will have:

- a tag in version control,
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com>`_.


Prerequisites
-------------

Software
~~~~~~~~

- A web browser.
- `gsutil Python package <https://pypi.python.org/pypi/gsutil>`_ on your workstation.
- `Vagrant`_ (1.6.2 or newer)
- `VirtualBox`_
- `virtualenvwrapper`_

.. _`Vagrant`: https://docs.vagrantup.com/
.. _`VirtualBox`: https://www.virtualbox.org/
.. _`virtualenvwrapper`: https://virtualenvwrapper.readthedocs.org/en/latest/

Access
~~~~~~

- Access to `Google Cloud Storage`_ using `gsutil`_ on your workstation.
  Set up ``gsutil`` authentication by following the instructions from the following command:

  .. prompt:: bash $

      gsutil config

- Access to Amazon `S3`_ using `gsutil`_ on your workstation.
  Set ``aws_access_key_id`` and ``aws_secret_access_key`` in the ``[Credentials]`` section of ``~/.boto``.

- A member of a `ClusterHQ team on Atlas <https://atlas.hashicorp.com/settings/organizations/clusterhq/teams/>`_.

- An OS X (most recent release) system.

.. note:: For a documentation release, access to Google Cloud Storage and Atlas is not required.

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

#. If this is a maintenance release, announce on Zulip's Engineering > Maintenance Release topic that a maintenance release is in progress.

   ::

      @engineering I am releasing from release/flocker-0.3.2. Please don't land anything on that branch until the release is complete.

#. Create a clean, local Flocker release branch with no modifications:

   .. note::

      For a maintenance release, replace ``origin/master`` below with ``origin/flocker-${BASE_VERSION}``,
      where ``${BASE_VERSION}`` is the release receiving the maintenance.

   .. prompt:: bash $

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      cd flocker-${VERSION}
      git checkout -b release/flocker-${VERSION} origin/master
      git push --set-upstream origin release/flocker-${VERSION}

#. Create and activate the Flocker release virtual environment:

   .. prompt:: bash $

      mkvirtualenv flocker-release-${VERSION}
      pip install --editable .[release]

#. Back port features from master (optional)

   The release may require certain changes to be back ported from the master branch.
   See :ref:`back-porting-changes`\ .

#. Ensure the release notes in :file:`NEWS` are up-to-date:

   XXX: Process to be decided.
   See https://clusterhq.atlassian.net/browse/FLOC-523

   - The NEWS date format is YYYY-MM-DD.
   - The NEWS file should also be updated for each pre-release and Weekly Development Release, however there should be only one NEWS entry for each Major Marketing Release and Minor Marketing Release.
   - This means that in doing a release, you may have to change the NEWS heading from a previous Weekly Development Release or pre-release.

   .. note:: ``git log`` can be used to see all merges between two versions.

            .. prompt:: bash $

                # Choose the tag of the last version with a "What's New" entry to compare the latest version to.
                export OLD_VERSION=0.3.0
                git log --first-parent ${OLD_VERSION}..release/flocker-${VERSION}

   .. prompt:: bash $

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

   .. prompt:: bash $

      git commit -am "Updated What's New"

#. Ensure copyright dates in :file:`LICENSE` are up-to-date:

   - The list of years near the end of :file:`LICENSE` should include each year in which commits were made to the project.
   - This is already the case up to and including 2015.
   - If any such years are not present in the list, add them and commit the changes:

   .. prompt:: bash $

      git commit -am "Updated copyright"

#. Push the changes:

   .. prompt:: bash $

      git push

#. Ensure all the tests pass on BuildBot:

   Go to the `BuildBot web status`_ and force a build on the just-created branch.

   In addition, review the link-check step of the documentation builder to ensure that all the errors (the links with "[broken]") are expected.

#. Update the staging documentation.
   (For a documentation release ``${VERSION}`` should be the base release version in this step).

   .. prompt:: bash $

      admin/publish-docs --doc-version ${VERSION}

#. Make a pull request on GitHub

   The pull request should be for the release branch against ``master``, with a ``[FLOC-123]`` summary prefix, referring to the release issue that it resolves.

   Wait for an accepted code review before continuing.

   .. warning:: Add a note to the pull request description explaining that the branch should not be merged until the release process is complete.


.. _pre-tag-review:

Pre-tag Review Process
----------------------

A tag cannot be deleted once it has been pushed to GitHub (this is a policy and not a technical limitation).
So it is important to check that the code in the release branch is working before it is tagged.

.. note::

   Make sure to follow the latest version of this documentation when reviewing a release.

#. Check documentation.

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

#. Update GitHub:

   If there are no problems spotted, comment on the Pull Request that the release engineer can continue by following :ref:`the Release section <release>` (do not merge the pull request).
   Otherwise, add comments to the Pull Request for any problems, and comment that they must be resolved before repeating this review process.

#.  Reject the JIRA issue.

    This is necessary because the release branch will need another review.

.. _release:

Release
-------

#. Create and log in to a new :doc:`Flocker development machine <vagrant>` using SSH agent forwarding so that you can push changes to GitHub using the keys from your workstation.

   From the cloned Flocker repository created in :ref:`preparing-for-a-release`:

   .. prompt:: bash $

      vagrant up
      vagrant ssh -- -A

#. Export the version number of the release being completed as an environment variable for later use:

   .. prompt:: bash [vagrant@localhost]$

      export VERSION=0.1.2

#. Create a clean, local copy of the Flocker and `homebrew-tap`_ release branches with no modifications:

   .. prompt:: bash [vagrant@localhost]$

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      git clone git@github.com:ClusterHQ/homebrew-tap.git "homebrew-tap-${VERSION}"
      cd homebrew-tap-${VERSION}
      git checkout -b release/flocker-${VERSION} origin/master
      git push --set-upstream origin release/flocker-${VERSION}
      cd ../flocker-${VERSION}
      git checkout release/flocker-${VERSION}

#. Create and activate the Flocker release virtual environment:
   
   .. note:: The final command ensures that setuptools is a version that does not normalize version numbers according to PEP440.

   .. prompt:: bash [vagrant@localhost]$

      mkvirtualenv flocker-release-${VERSION}
      pip install --editable .[release]
      pip install setuptools==3.6

#. Tag the version being released:

   .. prompt:: bash [vagrant@localhost]$

      git tag --annotate "${VERSION}" "release/flocker-${VERSION}" -m "Tag version ${VERSION}"
      git push origin "${VERSION}"

#. Go to the `BuildBot web status`_ and force a build on the tag.

   Force a build on a tag by putting the tag name (e.g. ``0.2.0``) into the branch box (without any prefix).

   .. note:: We force a build on the tag as well as the branch because the RPMs built before pushing the tag won't have the right version.
             Also, the RPM upload script currently expects the RPMs to be built from the tag, rather than the branch.

   Wait for the build to complete successfully.

#. Set up Google Cloud Storage credentials on the Vagrant development machine:

   .. prompt:: bash [vagrant@localhost]$

      gsutil config

   Set ``aws_access_key_id`` and ``aws_secret_access_key`` in the ``[Credentials]`` section of ``~/.boto`` to allow access to Amazon `S3`_ using `gsutil`_.

#. Build Python packages and upload them to ``archive.clusterhq.com``

   .. note:: Skip this step for a documentation release.

   .. prompt:: bash [vagrant@localhost]$

      python setup.py sdist bdist_wheel
      gsutil cp -a public-read "dist/Flocker-${VERSION}.tar.gz" "dist/Flocker-${VERSION}-py2-none-any.whl" gs://archive.clusterhq.com/downloads/flocker/

#. Build RPM packages and upload them to ``archive.clusterhq.com``

   .. note:: Skip this step for a documentation release.

   .. prompt:: bash [vagrant@localhost]$

      admin/upload-rpms "${VERSION}"

#. Copy the tutorial box to the final location:
   
   .. note:: Skip this step for a documentation release.

   .. prompt:: bash [vagrant@localhost]$

      gsutil cp -a public-read gs://clusterhq-vagrant-buildbot/tutorial/flocker-tutorial-${VERSION}.box gs://clusterhq-vagrant/flocker-tutorial-${VERSION}.box

#. Add the tutorial box to Atlas:

   .. note:: Skip this step for a documentation release.

   XXX This should be automated https://clusterhq.atlassian.net/browse/FLOC-943

   .. prompt:: bash [vagrant@localhost]$

      echo http://storage.googleapis.com/clusterhq-vagrant/flocker-tutorial-${VERSION}.box

   Use the echoed URL as the public link to the Vagrant box, and perform the steps to :ref:`add-vagrant-box-to-atlas`.

#. Create a version specific ``Homebrew`` recipe for this release:

   .. note:: Skip this step for a documentation release.

   XXX This should be automated https://clusterhq.atlassian.net/browse/FLOC-1150

   - Create a recipe file and push it to the `homebrew-tap`_ repository:

     .. prompt:: bash [vagrant@localhost]$

        cd ../homebrew-tap-${VERSION}
        ../flocker-${VERSION}/admin/make-homebrew-recipe > flocker-${VERSION}.rb
        git add flocker-${VERSION}.rb
        git commit -m "New Homebrew recipe"
        git push

   - Test the new recipe on OS X with `Homebrew`_ installed:

     Try installing the new recipe directly from a GitHub link

     .. prompt:: bash $

        brew install --verbose --debug https://raw.githubusercontent.com/ClusterHQ/homebrew-tap/release/flocker-${VERSION}/flocker-${VERSION}.rb
        brew test flocker-${VERSION}

   - Make a pull request:

     Make a `homebrew-tap`_ pull request for the release branch against ``master``, with a ``[FLOC-123]`` summary prefix, referring to the release issue that it resolves.

     Include the ``brew install`` line from the previous step, so that the reviewer knows how to test the new recipe.

   - Do not continue until the pull request is merged.
     Otherwise the documentation will refer to an unavailable ``Homebrew`` recipe.

#. Update the documentation.

   .. prompt:: bash [vagrant@localhost]$

      admin/publish-docs --production

#. Submit the release pull request for review again.

Post-Release Review Process
---------------------------

#. Check that the documentation is set up correctly:

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

#. Verify that the tutorial works on all supported platforms:

   * The client (``flocker-deploy``) should be installed on all supported platforms.

     Follow the :ref:`Flocker client installation documentation<installing-flocker-cli>`.

     XXX: This step should be automated. See `FLOC-1039 <https://clusterhq.atlassian.net/browse/FLOC-1039>`_.

   * The node package (``flocker-node``) should be installed on all supported platforms.
     You can use vagrant to boot a clean Fedora 20 machine as follows:

     .. prompt:: bash $

        mkdir /tmp/fedora20
        cd /tmp/fedora20
        vagrant init clusterhq/fedora20-updated
        vagrant up
        vagrant ssh

     Follow the :ref:`Flocker node installation documentation<installing-flocker-node>`.

     XXX: These steps should be automated. See (
     `FLOC-965 <https://clusterhq.atlassian.net/browse/FLOC-965>`_,
     `FLOC-957 <https://clusterhq.atlassian.net/browse/FLOC-957>`_,
     `FLOC-958 <https://clusterhq.atlassian.net/browse/FLOC-958>`_
     ).

   * Follow the :doc:`../../indepth/tutorial/vagrant-setup` part of the tutorial to make sure that the Vagrant nodes start up correctly.
   * Follow the :doc:`ELK example documentation<../../indepth/examples/linking>` using a Linux client installation and Rackspace Fedora20 nodes.

#. Merge the release pull request.

#. If this is a maintenance release, announce on Zulip's Engineering > Maintenance Release topic that the maintenance release is in complete.

   ::

      @engineering The release from release/flocker-0.3.2 is complete. Branches targeting it can now land.


Improving the Release Process
-----------------------------

The release engineer should aim to spend up to one day improving the release process in whichever way they find most appropriate.
If there is no existing issue for the planned improvements then a new one should be made.
Search for "labels = release_process AND status != done" to find existing issues relating to the release process.
The issue(s) for the planned improvements should be put into the next sprint.


.. _back-porting-changes:


Appendix: Back Porting Changes From Master
------------------------------------------

XXX: This process needs documenting. See https://clusterhq.atlassian.net/browse/FLOC-877


.. _gsutil: https://developers.google.com/storage/docs/gsutil
.. _wheel: https://pypi.python.org/pypi/wheel
.. _Google cloud storage: https://console.developers.google.com/project/apps~hybridcluster-docker/storage/archive.clusterhq.com/
.. _homebrew-tap: https://github.com/ClusterHQ/homebrew-tap
.. _BuildBot web status: http://build.clusterhq.com/boxes-flocker
.. _virtualenv: https://pypi.python.org/pypi/virtualenv
.. _Homebrew: http://brew.sh
.. _CloudFront: https://console.aws.amazon.com/cloudfront/home
.. _S3: https://console.aws.amazon.com/s3/home
