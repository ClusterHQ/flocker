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
- a Vagrant base tutorial image and
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com>`_.
- an updated Homebrew recipe


Prerequisites
-------------

Software
~~~~~~~~

- A :doc:`Flocker development machine <vagrant>`.
- A web browser.
- An up-to-date clone of the `Flocker repository <https://github.com/ClusterHQ/flocker.git>`_.
- An up-to-date clone of the `homebrew-tap repository <https://github.com/ClusterHQ/homebrew-tap.git>`_.

Access
~~~~~~

- A Read the Docs account (`registration <https://readthedocs.org/accounts/signup/>`_),
  with `maintainer access <https://readthedocs.org/dashboard/flocker/users/>`_ to the Flocker project.
- Access to `Google Cloud Storage`_ using `gsutil`_.
- A member of a `ClusterHQ team on Vagrant Cloud <https://vagrantcloud.com/settings/organizations/clusterhq/teams>`_.
- An OS X (most recent release) system.

Preparing For a Release
-----------------------

#. Confirm that the release and the proposed version number have been approved.

   The release must have been approved.
   Refer to the ClusterHQ `Flocker Releases and Versioning <https://docs.google.com/a/clusterhq.com/document/d/1xYbcU6chShgQQtqjFPcU1rXzDbi6ZsIg1n0DZpw6FfQ>`_ policy document.

   The version number must adhere to :ref:`the Flocker version numbering policy <version-numbers>`.

#. Export the version number of the release being created as an environment variable for later use:

   .. code-block:: console

      export VERSION=0.1.2

#. Create an issue:

   #. Set the title to "Release Flocker $VERSION"
   #. Assign it to yourself

#. Create a clean, local Flocker release branch with no modifications:

   .. code-block:: console

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      cd flocker-${VERSION}
      git checkout -b release/flocker-${VERSION} origin/master
      git push origin --set-upstream release/flocker-${VERSION}

#. Back port features from master (optional)

   The release may require certain changes to be back ported from the master branch.
   See :ref:`back-porting-changes`\ .

#. Update the version numbers in:

   - the ``pip install`` line in
     `docs/gettingstarted/linux-install.sh <https://github.com/ClusterHQ/flocker/blob/master/docs/gettingstarted/linux-install.sh>`_,
   - the ``box_version`` in
     `docs/gettingstarted/tutorial/Vagrantfile <https://github.com/ClusterHQ/flocker/blob/master/docs/gettingstarted/tutorial/Vagrantfile>`_,
   - `docs/gettingstarted/installation.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/gettingstarted/installation.rst>`_ (including the sample command output) and

   Commit the changes:

   .. code-block:: console

      $ git commit -am "Bumped version numbers"

   .. This should be automated. See https://clusterhq.atlassian.net/browse/FLOC-1038

#. Ensure the release notes in :file:`NEWS` are up-to-date:

   XXX: Process to be decided.
   See https://clusterhq.atlassian.net/browse/FLOC-523

   - The NEWS date format is YYYY-MM-DD.
   - The NEWS file should also be updated for each pre-release and Weekly Development Release, however there should be only one NEWS entry for each Major Marketing Release and Minor Marketing Release.
   - This means that in doing a release, you may have to change the NEWS heading from a previous Weekly Development Release or pre-release.

   .. note:: ``git log`` can be used to see all merges between two versions.

             .. code-block:: console

                # Choose the tag of the last version with a "What's New" entry to compare the latest version to.
                $ export OLD_VERSION=0.3.0
                $ git log --first-parent ${OLD_VERSION}..release/flocker-${VERSION}

   .. code-block:: console

      $ git commit -am "Updated NEWS"

#. Ensure the notes in `docs/advanced/whatsnew.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/advanced/whatsnew.rst>`_ are up-to-date:

   - Update the "What's New" document.
   - (optional) Add a version heading.
     If this is a Major or Minor Marketing (pre-)release, the "What's New" document should have a heading corresponding to the release version.
     If this is a weekly development release, add a "Next Release" heading instead.
   - Refer to the appropriate internal release planning document for a list of features that were scheduled for this release, e.g. Product Development > Releases > Release 0.3.1, and add bullet points for those features that have been completed.
   - Add bullet points for any other *important* new features and improvements from the NEWS file above,
   - and add links (where appropriate) to documentation that has been added for those features.

   Finally, commit the changes:

   .. code-block:: console

      $ git commit -am "Updated What's New"

#. Ensure copyright dates in :file:`LICENSE` are up-to-date:

   - The list of years near the end of :file:`LICENSE` should include each year in which commits were made to the project.
   - If any such years are not present in the list, add them and commit the changes:

   .. code-block:: console

      git commit -am "Updated copyright"

#. Push the changes:

   .. code-block:: console

      git push

#. Ensure all the tests pass on BuildBot:

   Go to the `BuildBot web status`_ and force a build on the just-created branch.

   In addition, review the link-check step of the documentation builder to ensure that all the errors are expected.

#. Make a pull request on GitHub

   The pull request should be for the release branch against ``master``, with a ``[FLOC-123]`` summary prefix, referring to the release issue that it resolves.

   Wait for an accepted code review before continuing.

   .. warning:: Add a note to the pull request description explaining that the branch should not be merged until the release process is complete.


.. _pre-tag-review:

Pre-tag Review Process
----------------------

A tag cannot be deleted once it has been pushed to GitHub (this is a policy and not a technical limitation).
So it is important to check that the code in the release branch is working before it is tagged.
This review step is to ensure that all acceptance tests pass on the release branch before it is tagged.

.. note::

   Make sure to follow the latest version of this documentation when reviewing a release.

.. warning:: This process requires ``Vagrant`` and should be performed on your own workstation;
            **not** on a :doc:`Flocker development machine <vagrant>`.

#. Export the version number of the release being reviewed as an environment variable for later use:

   .. code-block:: console

      export VERSION=0.1.2

#. Do the acceptance tests:

   - Add the tutorial vagrant box that BuildBot has created from the release branch.

     .. code-block:: console

        vagrant box add http://build.clusterhq.com/results/vagrant/release/flocker-${VERSION}/flocker-tutorial.json

     You should now see the ``flocker-tutorial`` box listed:

     .. code-block:: console
        :emphasize-lines: 4

        $ vagrant box list
        clusterhq/fedora20-updated (virtualbox, 2014.09.19)
        clusterhq/flocker-dev      (virtualbox, 0.2.1.263.g572d20f)
        clusterhq/flocker-tutorial (virtualbox, <RELEASE_BRANCH_VERSION>)

   - Clone Flocker on your local workstation and install all ``dev`` requirements:

     .. note:: The following instructions use `virtualenvwrapper`_ but you can use `virtualenv`_ directly if you prefer.

     .. code-block:: console

        git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
        cd "flocker-${VERSION}"
        git checkout "release/flocker-${VERSION}"
        mkvirtualenv "flocker-release-${VERSION}"
        pip install --editable .[dev]

   - Install `PhantomJS`_:

     On Linux you will need to ensure that that the ``phantomjs`` binary is on your ``PATH`` before running the acceptance tests below.

   - Add the Vagrant key to your agent:

     .. code-block:: console

        ssh-add ~/.vagrant.d/insecure_private_key

   - Run the automated acceptance tests.

     They will start the appropriate VMs.
     Ensure that they all pass, with no skips:

     .. code-block:: console

        $ admin/run-acceptance-tests --distribution fedora-20

#. Accept or reject the release issue depending on whether everything has worked.

   - If accepting the issue, comment that the release engineer can continue by following :ref:`the Release section <release>` (do not merge the pull request).

   - If rejecting the issue, any problems must be resolved before repeating the review process.

.. _PhantomJS: http://phantomjs.org/download.html

.. _release:

Release
-------

.. warning:: The following steps should be carried out on a :doc:`Flocker development machine <vagrant>`.
             Log into the machine using SSH agent forwarding so that you can push changes to GitHub using the keys from your workstation.

             .. code-block:: console

                vagrant ssh -- -A

#. Export the version number of the release being completed as an environment variable for later use:

   .. code-block:: console

      export VERSION=0.1.2

#. Create a clean, local copy of the Flocker and `homebrew-tap`_ release branches with no modifications:

   .. code-block:: console

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      git clone git@github.com:ClusterHQ/homebrew-tap.git "homebrew-tap-${VERSION}"
      cd homebrew-tap-${VERSION}
      git checkout -b release/flocker-${VERSION} origin/master
      git push origin --set-upstream release/flocker-${VERSION}
      cd ../flocker-${VERSION}
      git checkout release/flocker-${VERSION}

#. Create and activate the Flocker release virtual environment:

   .. note:: The following instructions use `virtualenvwrapper`_ but you can use `virtualenv`_ directly if you prefer.

   .. code-block:: console

      mkvirtualenv flocker-release-${VERSION}
      pip install --editable .[release]

#. Tag the version being released:

   .. code-block:: console

      git tag --annotate "${VERSION}" "release/flocker-${VERSION}" -m "Tag version ${VERSION}"
      git push origin "${VERSION}"

#. Go to the `BuildBot web status`_ and force a build on the tag.

   Force a build on a tag by putting the tag name (e.g. ``0.2.0``) into the branch box (without any prefix).

   .. note:: We force a build on the tag as well as the branch because the RPMs built before pushing the tag won't have the right version.
             Also, the RPM upload script currently expects the RPMs to be built from the tag, rather than the branch.

   Wait for the build to complete successfully.

#. Build Python packages and upload them to ``archive.clusterhq.com``

   .. code-block:: console

      python setup.py sdist bdist_wheel
      gsutil cp -a public-read \
          "dist/Flocker-${VERSION}.tar.gz" \
          "dist/Flocker-${VERSION}-py2-none-any.whl" \
          gs://archive.clusterhq.com/downloads/flocker/


   .. note:: Set up ``gsutil`` authentication by following the instructions from the following command:

             .. code-block:: console

                $ gsutil config

#. Build RPM packages and upload them to ``archive.clusterhq.com``

   .. code-block:: console

      admin/upload-rpms "${VERSION}"

#. Build and upload the tutorial :ref:`Vagrant box <build-vagrant-box>`.

   .. warning:: This step requires ``Vagrant`` and should be performed on your own workstation;
                **not** on a :doc:`Flocker development machine <vagrant>`.
                This means that ``gsutil`` must be installed and configured on your workstation.

#. Create a version specific ``Homebrew`` recipe for this release:

   XXX This should be automated https://clusterhq.atlassian.net/browse/FLOC-1150

   - Create a recipe file and push it to the `homebrew-tap`_ repository:

     .. code-block:: console

        cd ../homebrew-tap-${VERSION}
        ../flocker-${VERSION}/admin/make-homebrew-recipe > flocker-${VERSION}.rb
        git add flocker-${VERSION}.rb
        git commit -m "New Homebrew recipe"
        git push

   - Test the new recipe on OS X with `Homebrew`_ installed:

     Try installing the new recipe directly from a GitHub link

     .. code-block:: console

        brew install --verbose --debug https://raw.githubusercontent.com/ClusterHQ/homebrew-tap/release/flocker-${VERSION}/flocker-${VERSION}.rb
        brew test flocker-${VERSION}.rb

   - Make a pull request:

     Make a `homebrew-tap`_ pull request for the release branch against ``master``, with a ``[FLOC-123]`` summary prefix, referring to the release issue that it resolves.

     Include the ``brew install`` line from the previous step, so that the reviewer knows how to test the new recipe.

   - Do not continue until the pull request is merged.
     Otherwise the documentation will refer to an unavailable ``Homebrew`` recipe.

#. Build tagged docs at Read the Docs:

   #. Force Read the Docs to reload the repository

      There is a GitHub webhook which should notify Read The Docs about changes in the Flocker repository, but it sometimes fails.
      Force an update by running:

      .. code-block:: console

         curl -X POST http://readthedocs.org/build/flocker

   #. Go to the `Read the Docs dashboard Versions section`_.
   #. Set the version being released to be "Active".
   #. Unset "Active" for each previous weekly release or pre-release of the version being released.
   #. Wait for the documentation to build.
      The documentation will be visible at http://docs.clusterhq.com/en/${VERSION} when it has been built.
   #. Set the default version and latest version to that version:

      .. warning:: Skip this step for weekly releases and pre-releases.
                   The features and documentation in weekly releases and pre-releases may not be complete and may not have been tested.
                   We want new users' first experience with Flocker to be as smooth as possible so we direct them to the tutorial for the last stable release.
                   Other users choose to try the weekly releases, by clicking on the latest weekly version in the ReadTheDocs version panel.

      - In the `Read the Docs dashboard Versions section`_ set the "Default Version" dropdown to the version being released.

      - In the `Advanced Settings section <https://readthedocs.org/dashboard/flocker/advanced/>`_ change the "Default branch" to the version being released.

      - In the `Builds section <https://readthedocs.org/builds/flocker/>`_ "Build Version" with "latest" selected in the dropdown.
        Wait for the new HTML build to pass.

#. Submit the release pull request for review again.

Post-Release Review Process
---------------------------

#. Remove the Vagrant box which was added as part of :ref:`pre-tag-review`:

   .. code-block:: console

      $ vagrant box remove clusterhq/flocker-tutorial

#. Check that Read The Docs is set up correctly:

   The following links should both point to the latest release.
   (Except in the case of weekly release or pre-release)

   * https://docs.clusterhq.com/en/latest and
   * https://docs.clusterhq.com/

#. Verify that the tutorial works on all supported platforms:

   * The client (``flocker-deploy``) should be installed on all supported platforms.

     Follow the :ref:`Flocker client installation documentation<installing-flocker-cli>`.

     XXX: This step should be automated. See `FLOC-1039 <https://clusterhq.atlassian.net/browse/FLOC-1039>`_.

   * The node package (``flocker-node``) should be installed on all supported platforms.
     You can use vagrant to boot a clean Fedora 20 machine as follows:

     .. code-block:: console

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

   * Follow the :doc:`../../gettingstarted/tutorial/vagrant-setup` part of the tutorial to make sure that the Vagrant nodes start up correctly.
   * Follow the :doc:`ELK example documentation<../../gettingstarted/examples/linking>` using a Linux client installation and Rackspace Fedora20 nodes.

#. Merge the release pull request.


.. _Read the Docs dashboard Versions section: https://readthedocs.org/dashboard/flocker/versions/


Improving the Release Process
-----------------------------

The release engineer should aim to spend up to one day improving the release process in whichever way they find most appropriate.
If there is no existing issue for the planned improvements then a new one should be made.
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
.. _virtualenvwrapper: https://pypi.python.org/pypi/virtualenvwrapper
.. _virtualenv: https://pypi.python.org/pypi/virtualenv
.. _Homebrew: http://brew.sh
