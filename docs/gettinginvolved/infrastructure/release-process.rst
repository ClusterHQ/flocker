Release Process
===============

.. note::

   Make sure to follow the `latest documentation`_ when doing a release.

.. _latest documentation: http://doc-dev.clusterhq.com/gettinginvolved/infrastructure/release-process.html


Outcomes
--------

By the end of the release process we will have:

- a tag in version control
- a Python wheel in the `ClusterHQ package index <http://archive.clusterhq.com>`_
- Fedora 20 RPMs for software on the node and client
- a Vagrant base tutorial image
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com>`_


Prerequisites
-------------

Software
~~~~~~~~

- A :doc:`Flocker development machine <vagrant>` which has the following commands:

  - ``rpmbuild``
  - ``createrepo``
  - ``yumdownloader``

- a web browser

- an up-to-date clone of the `Flocker repository <https://github.com/ClusterHQ/flocker.git>`_

- an up-to-date clone of the `homebrew-tap repository <https://github.com/ClusterHQ/homebrew-tap.git>`_

Access
~~~~~~

- A Read the Docs account (`registration <https://readthedocs.org/accounts/signup/>`_),
  with `maintainer access <https://readthedocs.org/dashboard/flocker/users/>`_ to the Flocker project.

- Access to `Google Cloud Storage`_ using `gsutil`_.


Preparing for a release
-----------------------

.. warning:: The following steps should be carried out on a :doc:`Flocker development machine <vagrant>`.
             Log into the machine using SSH agent forwarding so that you can push changes to GitHub using the keys from your workstation.

             .. code-block:: console

                vagrant ssh -- -A

#. Choose a version number:

   - Release numbers should be of the form x.y.z e.g.:

     .. code-block:: console

        export VERSION=0.1.2

#. Create an issue:

   #. Set the title to "Release flocker $VERSION"
   #. Assign it to yourself

#. Create a clean, local working copy of Flocker with no modifications:

   .. code-block:: console

      git clone git@github.com:ClusterHQ/flocker.git "flocker-${VERSION}"

#. Check that all required versions of the dependency packages are built:

   #. Inspect the package versions listed in the ``install_requires`` section of ``setup.py``.
   #. Check that matching RPM packages are available on the ``clusterhq`` repository.
      You can list the current contents of the ``clusterhq`` repository using the following command on Fedora.

      .. code-block:: console

         repoquery --repoid clusterhq --repofrompath clusterhq,http://archive.clusterhq.com/fedora/20/x86_64/ "*"

#. Create a branch for the release and push it to GitHub:

   .. code-block:: console

      git checkout -b release/flocker-${VERSION} origin/master
      git push origin --set-upstream release/flocker-${VERSION}

#. Back port features from master (optional)

   The release may require certain changes to be back ported from the master branch.
   See :ref:`back-porting-changes`\ .

#. Update the version numbers in:

   - the ``yum install`` line in
     `docs/gettingstarted/linux-install.sh <https://github.com/ClusterHQ/flocker/blob/master/docs/gettingstarted/linux-install.sh>`_ and
   - the ``box_version`` in
     `docs/gettingstarted/tutorial/Vagrantfile <https://github.com/ClusterHQ/flocker/blob/master/docs/gettingstarted/tutorial/Vagrantfile>`_
   - `docs/gettingstarted/installation.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/gettingstarted/installation.rst>`_ (including the sample command output)
   - The "Next Release" line in
     `docs/advanced/whatsnew.rst <https://github.com/ClusterHQ/flocker/blob/master/docs/advanced/whatsnew.rst>`_
   - Commit the changes:

     .. code-block:: console

        git commit -am "Bumped version numbers"

#. Ensure the release notes in :file:`NEWS` are up-to-date:

   XXX: Process to be decided.
   See https://github.com/ClusterHQ/flocker/issues/523

   .. code-block:: console

      git commit -am "Updated NEWS"

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

#. Do the acceptance tests:

   XXX: See https://github.com/ClusterHQ/flocker/issues/315

#. Make a pull request on GitHub

   The pull request should be for the release branch against ``master``, with a ``Fixes #123`` line in the description referring to the release issue that it resolves.

   Wait for an accepted code review before continuing.

   .. warning:: Do not merge the branch yet.
                It should only be merged once it has been tagged, in the next series of steps.

Release
-------

.. warning:: The following steps should be carried out on a :doc:`Flocker development machine <vagrant>`.
             Log into the machine using SSH agent forwarding so that you can push changes to GitHub using the keys from your workstation.

             .. code-block:: console

                vagrant ssh -- -A

#. Change your working directory to be the Flocker release branch working directory.

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

#. Build python packages and upload them to ``archive.clusterhq.com``

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

#. Build and upload the tutorial :ref:`vagrant box <build-vagrant-box>`.

#. Build tagged docs at Read the Docs:

   #. Force Read the Docs to reload the repository

      There is a GitHub webhook which should notify Read The Docs about changes in the Flocker repository, but it sometimes fails.
      Force an update by running:

      .. code-block:: console

         curl -X POST http://readthedocs.org/build/flocker

   #. Go to the `Read the Docs dashboard <https://readthedocs.org/dashboard/flocker/versions/>`_.
   #. Enable the version being released.
   #. Wait for the documentation to build.
      The documentation will be visible at http://docs.clusterhq.com/en/${VERSION} when it has been built.
   #. Set the default version to that version.

      .. warning:: Skip this step for weekly releases and pre-releases.
                   The features and documentation in weekly releases and pre-releases may not be complete and may not have been tested.
                   We want new users' first experience with Flocker to be as smooth as possible so we direct them to the tutorial for the last stable release.
                   Other users choose to try the weekly releases, by clicking on the latest weekly version in the ReadTheDocs version panel.

#. Update the Homebrew recipe

   The aim of this step is to provide a version specific ``homebrew`` recipe for each release.

   - Checkout the `homebrew-tap`_ repository.

     .. code-block:: console

        git clone git@github.com:ClusterHQ/homebrew-tap.git

   - Create a release branch

     .. code-block:: console

        git checkout -b release/flocker-${VERSION%pre*} origin/master
        git push origin --set-upstream release/flocker-${VERSION%pre*}

   - Create a ``flocker-${VERSION}.rb`` file

     Copy the last recipe file and rename it for this release.

   - Update recipe file

     - Update the version number

       The version number is included in the class name with all dots and dashes removed.
       e.g. ``class Flocker012 < Formula`` for Flocker-0.1.2

     - Update the URL

       The version number is also included in the ``url`` part of the recipe.

     - Update the ``sha1`` checksum.

       .. code-block:: console

          sha1sum "dist/Flocker-${VERSION}.tar.gz"
          ed03a154c2fdcd19eca471c0e22925cf0d3925fb  dist/Flocker-0.1.2.tar.gz

     - Commit the changes and push

       .. code-block:: console

          git commit -am "Bumped version number and checksum in homebrew recipe"
          git push

   - Test the new recipe on OS X with `Homebrew`_ installed

     Try installing the new recipe directly from a GitHub link

     .. code-block:: console

        brew install https://raw.githubusercontent.com/ClusterHQ/homebrew-tap/release/flocker-${VERSION}/flocker-${VERSION}.rb

   - Make a pull request

     Make a `homebrew-tap`_ pull request for the release branch against ``master``, with a ``Refs #123`` line in the description referring to the release issue that it resolves.

#. Merge the release branch

   Merge release branch and close the release pull request.


.. _back-porting-changes:

Appendix: Back Porting Changes From Master
------------------------------------------

XXX: This process needs documenting. See https://github.com/ClusterHQ/flocker/issues/877


.. _pre-populating-rpm-repository:

Appendix: Pre-populating RPM Repository
-----------------------------------------------

.. warning:: This only needs to be done if the dependency packages for Flocker (e.g. 3rd party Python libraries) change; it should *not* be done every release.
             If you do run this you need to do it *before* running the release process above as it removes the ``flocker-cli`` etc. packages from the repository!

These steps must be performed from a machine with the ClusterHQ Copr repository installed.
You can either use the :doc:`Flocker development environment <vagrant>`
or install the Copr repository locally by running

.. code-block:: console
   curl https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/repo/fedora-20-x86_64/tomprince-hybridlogic-fedora-20-x86_64.repo >/etc/yum.repos.d/hybridlogic.repo

The steps are:

- download all the latest binary and source packages from the Copr repository,
- create a local repository,
- upload to Google Cloud Storage using ``gsutil``.

::

   mkdir repo
   yumdownloader --destdir=repo python-characteristic python-eliot python-idna python-netifaces python-service-identity python-treq python-twisted python-docker-py
   createrepo repo
   gsutil cp -a public-read -R repo gs://archive.clusterhq.com/fedora/20/x86_64


::

   mkdir srpm
   yumdownloader --destdir=srpm --source python-characteristic python-eliot python-idna python-netifaces python-service-identity python-treq python-twisted python-docker-py
   createrepo srpm
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
