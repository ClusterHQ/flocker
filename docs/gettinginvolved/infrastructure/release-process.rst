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
- A member of a `ClusterHQ team on Vagrant Cloud <https://vagrantcloud.com/organization/clusterhq/teams>`_


Preparing For a Release
-----------------------

#. Choose a version number according to :ref:`the Flocker version numbering policy <version-numbers>`.

#. Export the version number as an environment variable for later use:

   .. code-block:: console

      export VERSION=0.1.2

#. Create an issue:

   #. Set the title to "Release flocker $VERSION"
   #. Assign it to yourself

#. Create a clean, local Flocker release branch with no modifications:

   .. code-block:: console

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      cd flocker-${VERSION}
      git checkout -b release/flocker-${VERSION} origin/master
      git push origin --set-upstream release/flocker-${VERSION}

#. Check that all required versions of the dependency packages are built:

   #. Inspect the package versions listed in the ``install_requires`` section of ``setup.py``.
   #. Compare it to the package versions listed in the "Requires" lines in ``python-flocker.spec.in``.
   #. If there are any mismatches, change ``python-flocker.spec.in`` appropriately, commit the changes, and add any missing package names to the lists of downloaded packages in :ref:`pre-populating-rpm-repository`.
      Also, upload the missing dependency packages as follows (we use the ``python-jsonschema`` package as an example):

   .. note:: XXX: Automate the checking of package versions.
             See https://github.com/ClusterHQ/flocker/issues/881.


   .. code-block:: console

      # Create directories for storing RPMs and SRPMs.
      mkdir repo
      mkdir srpm

      # Download binary and source RPM files to your workstation.
      yumdownloader --disablerepo='*' --enablerepo=tomprince-hybridlogic --destdir=repo python-jsonschema
      yumdownloader --disablerepo='*' --enablerepo=tomprince-hybridlogic --destdir=srpm --source python-jsonschema

      # Upload those to Google Storage
      gsutil cp -a public-read srpm/python-jsonschema-2.4.0-1.fc20.src.rpm gs://archive.clusterhq.com/fedora/20/SRPMS/
      gsutil cp -a public-read repo/python-jsonschema-2.4.0-1.fc20.noarch.rpm gs://archive.clusterhq.com/fedora/20/x86_64/

      # Finally we rebuild the repo index using the version
      # number of the *last* Flocker release.
      admin/upload-rpms 0.3.0dev1

   This step will not be necessary once https://github.com/ClusterHQ/flocker/issues/508 is resolved.

#. Back port features from master (optional)

   The release may require certain changes to be back ported from the master branch.
   See :ref:`back-porting-changes`\ .

#. Update the version numbers in:

   - the ``pip install`` line in
     `docs/gettingstarted/linux-install.sh <https://github.com/ClusterHQ/flocker/blob/master/docs/gettingstarted/linux-install.sh>`_,
   - the ``box_version`` in
     `docs/gettingstarted/tutorial/Vagrantfile <https://github.com/ClusterHQ/flocker/blob/master/docs/gettingstarted/tutorial/Vagrantfile>`_,
   - `docs/gettingstarted/installation.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/gettingstarted/installation.rst>`_ (including the sample command output) and
   - the "Next Release" line in
     `docs/advanced/whatsnew.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/advanced/whatsnew.rst>`_.
   - Commit the changes:

     .. code-block:: console

        git commit -am "Bumped version numbers"

#. Ensure the notes in `docs/advanced/whatsnew.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/advanced/whatsnew.rst>`_ are up-to-date:

   Update "What's New" and commit changes:

   .. code-block:: console

      $ git commit -am "Updated What's New"

#. Ensure the release notes in :file:`NEWS` are up-to-date:

   XXX: Process to be decided.
   See https://github.com/ClusterHQ/flocker/issues/523

   The NEWS date format is YYYY-MM-DD.
   The NEWS file should be updated for each pre-release and weekly release, however there should be only one NEWS entry for each major release.
   This means that in doing a release, you may have to change the NEWS heading from a previous weekly or pre-release.

   ``git log`` can be used to see all merges between two versions.

   .. code-block:: console

      # Choose the tag of the last version with a "What's New" entry to compare the latest version to.
      $ export OLD_VERSION=0.3.0
      $ git log --first-parent ${OLD_VERSION}..release/flocker-${VERSION}

   Use the previously-saved logs to update "NEWS" and commit changes:

   .. code-block:: console

      $ git commit -am "Updated NEWS"

#. Ensure copyright dates in :file:`LICENSE` are up-to-date:

   XXX: Process to be decided.
   See https://github.com/ClusterHQ/flocker/issues/525

   .. code-block:: console

      git commit -am "Updated copyright"

#. Push the changes:

   .. code-block:: console

      git push

#. Ensure all the tests pass on BuildBot:

   Go to the `BuildBot web status`_ and force a build on the just-created branch.

#. Make a pull request on GitHub

   The pull request should be for the release branch against ``master``, with a ``Fixes FLOC-123`` line in the description referring to the release issue that it resolves.

   Wait for an accepted code review before continuing.

   .. warning:: Add a note to the pull request description explaining that the branch should not be merged until the release process is complete.


Reviewing "Preparing For a Release"
-----------------------------------

.. note::

   Make sure to follow the latest version of this documentation when reviewing a release.

.. warning:: This process requires ``Vagrant`` and should be performed on your own workstation;
            **not** on a :doc:`Flocker development machine <vagrant>`.

#. Do the acceptance tests:

   You'll need to build a tutorial vagrant image using the BuildBot RPM packages from the release branch.

   The RPM version will not yet correspond to the release version, because we haven't yet created a tag.

   To find the version, visit the BuildBot build results page and navigate to the ``flocker-rpms`` build, then click on ``stdio`` from the ``build-sdist`` step.

   At the top, you should find a line beginning ``got version`` which contains the version string.

   Export the ``final`` and ``got`` version numbers as an environment variable for later use:

   .. code-block:: console

      export VERSION=0.1.2
      export GOT_VERSION=0.2.1-378-gb59b886

   Clone Flocker on your local workstation and install all ``dev`` requirements:

   .. note:: The following instructions use `virtualenvwrapper`_ but you can use `virtualenv`_ directly if you prefer.

   .. code-block:: console

     git clone git@github.com:ClusterHQ/flocker.git
     cd flocker
     git checkout -b *release branch*
     mkvirtualenv flocker-release-${VERSION}
     pip install --editable .[dev]

   Then build the tutorial image and add the resulting box to ``vagrant``:

   .. code-block:: console

         cd vagrant/tutorial
         ./build --flocker-version=${GOT_VERSION} --branch=release/flocker-${VERSION}
         vagrant box add --name='clusterhq/flocker-tutorial'  flocker-tutorial-${GOT_VERSION}.box

      You should now see the ``flocker-tutorial`` box listed:

   .. code-block:: console
      :emphasize-lines: 4

      $ vagrant box list
      clusterhq/fedora20-updated (virtualbox, 2014.09.19)
      clusterhq/flocker-dev      (virtualbox, 0.2.1.263.g572d20f)
      clusterhq/flocker-tutorial (virtualbox, 0)

   .. Renaming the file is necessary because Sphinx does not deal well with two files named the same, and there is already the tutorial Vagrantfile. See https://bitbucket.org/birkenfeld/sphinx/issue/823/i-wish-download-would-keep-the-paths-not

   Download the :download:`acceptance testing Vagrantfile <acceptance-Vagrantfile>` to a new directory and rename it ``Vagrantfile``.

   Follow the :doc:`../../gettingstarted/tutorial/vagrant-setup` steps of the tutorial with a few changes:

   - Instead of downloading the tutorial's ``Vagrantfile``, use the acceptance testing ``Vagrantfile``.
   - Substitute the tutorial Vagrant nodes' IP addresses (172.16.255.250 and 172.16.255.251) with the acceptance testing nodes' IP addresses (172.16.255.240 and 172.16.255.241).

   Run the automated acceptance tests and ensure that they all pass, with no skips:

   .. code-block:: console

      $ trial flocker.acceptance

#. Accept or reject the release issue depending on whether everything has worked.

   - If accepting the issue, comment that the release engineer can continue by following :ref:`the Release section <release>` (do not merge the pull request).

   - If rejecting the issue, any problems must be resolved before repeating the review process.

.. _release:

Release
-------

.. warning:: The following steps should be carried out on a :doc:`Flocker development machine <vagrant>`.
             Log into the machine using SSH agent forwarding so that you can push changes to GitHub using the keys from your workstation.

             .. code-block:: console

                vagrant ssh -- -A

#. Create a clean, local copy of the Flocker release branch with no modifications:

   .. code-block:: console

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"
      cd flocker-${VERSION}
      git checkout release/flocker-${VERSION}

#. Export the version number as an environment variable for later use:

   .. code-block:: console

      export VERSION=0.1.2

#. Create (if necessary) and activate the Flocker release virtual environment:

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

#. Update the Homebrew recipe

   The aim of this step is to provide a version specific ``Homebrew`` recipe for each release.

   - Checkout the `homebrew-tap`_ repository:

     .. code-block:: console

        git clone git@github.com:ClusterHQ/homebrew-tap.git

   - Create a release branch:

     .. code-block:: console

        git checkout -b release/flocker-${VERSION} origin/master
        git push origin --set-upstream release/flocker-${VERSION}

   - Create a ``flocker-${VERSION}.rb`` file by copying the last recipe file and renaming it for this release.

   - Update recipe file:

     - Update the version number:

       The version number is included in the class name with all dots and dashes removed.
       e.g. ``class Flocker012 < Formula`` for Flocker-0.1.2

     - Update the URL:

       The version number is also included in the ``url`` part of the recipe.

     - Update the ``sha1`` checksum. Retrieve it with ``sha1sum``:

       .. code-block:: console

          sha1sum "dist/Flocker-${VERSION}.tar.gz"
          ed03a154c2fdcd19eca471c0e22925cf0d3925fb  dist/Flocker-0.1.2.tar.gz

     - Commit the changes and push:

       .. code-block:: console

          git add *new recipe*
          git commit -m "New Homebrew recipe with bumped version number and checksum"
          git push

   - Test the new recipe on OS X with `Homebrew`_ installed:

     Try installing the new recipe directly from a GitHub link

     .. code-block:: console

        brew install https://raw.githubusercontent.com/ClusterHQ/homebrew-tap/release/flocker-${VERSION}/flocker-${VERSION}.rb
        brew test flocker-${VERSION}.rb

   - Make a pull request:

     Make a `homebrew-tap`_ pull request for the release branch against ``master``, with a ``Refs FLOC-123`` line in the description referring to the release issue that it resolves.

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

Reviewing "Release"
-------------------

#. When the Release section has been completed, there will be a ``Homebrew`` pull request to review.
   See the "Update the Homebrew recipe" step in the Release section which explains how to test the new ``Homebrew`` recipe from a branch.

#. Remove the Vagrant box which was added as part of testing the "Preparing For a Release" section:

   .. code-block:: console

      $ vagrant box remove clusterhq/flocker-tutorial

#. Check that Read The Docs is set up correctly.
   https://docs.clusterhq.com/en/latest and https://docs.clusterhq.com/ should both point to the latest release which is not a weekly release or pre-release.

#. Follow the Vagrant setup part of the tutorial to make sure that the Vagrant nodes start up correctly.

#. Merge the release pull request.


.. _Read the Docs dashboard Versions section: https://readthedocs.org/dashboard/flocker/versions/

.. _back-porting-changes:

Appendix: Back Porting Changes From Master
------------------------------------------

XXX: This process needs documenting. See https://github.com/ClusterHQ/flocker/issues/877


.. _pre-populating-rpm-repository:

Appendix: Pre-populating RPM Repository
---------------------------------------

.. warning:: This only needs to be done if the dependency packages for Flocker (e.g. 3rd party Python libraries) change; it should *not* be done every release.
             If you do run this you need to do it *before* running the release process above as it removes the ``flocker-cli`` etc. packages from the repository index!

These steps must be performed from a :doc:`Flocker development environment <vagrant>` because it has the HybridLogic Copr repository pre-installed.

::

   mkdir repo
   mkdir srpm

   # Download all the latest binary and source packages from the Copr repository.
   yumdownloader --disablerepo='*' --enablerepo=tomprince-hybridlogic --destdir=repo python-characteristic python-eliot python-idna python-netifaces python-service-identity python-treq python-twisted python-docker-py python-psutil python-klein python-jsonschema
   yumdownloader --disablerepo='*' --enablerepo=tomprince-hybridlogic --destdir=srpm --source python-characteristic python-eliot python-idna python-netifaces python-service-identity python-treq python-twisted python-docker-py python-psutil python-klein python-jsonschema

   # Create local repositories.
   createrepo repo
   createrepo srpm

   # Upload to Google Cloud Storage using ``gsutil``.
   gsutil cp -a public-read -R repo gs://archive.clusterhq.com/fedora/20/x86_64
   gsutil cp -a public-read -R srpm gs://archive.clusterhq.com/fedora/20/SRPMS

.. note: XXX: Move or automate this documentation https://github.com/ClusterHQ/flocker/issues/327

.. _gsutil: https://developers.google.com/storage/docs/gsutil
.. _wheel: https://pypi.python.org/pypi/wheel
.. _Google cloud storage: https://console.developers.google.com/project/apps~hybridcluster-docker/storage/archive.clusterhq.com/
.. _homebrew-tap: https://github.com/ClusterHQ/homebrew-tap
.. _BuildBot web status: http://build.clusterhq.com/boxes-flocker
.. _virtualenvwrapper: https://pypi.python.org/pypi/virtualenvwrapper
.. _virtualenv: https://pypi.python.org/pypi/virtualenv
.. _Homebrew: http://brew.sh
