Release Process
===============

Outcomes
--------

By the end of the release process we will have:

- a tag in version control
- a Python wheel in the `ClusterHQ package index <http://archive.clusterhq.com>`__
- Fedora 20 RPMs for software on the node and client
- documentation on `docs.clusterhq.com <https://docs.clusterhq.com>`__
- announcement on mailing list, blog, IRC (others?)
- download links on clusterhq.com


Prerequisites
-------------

Software
~~~~~~~~

- Fedora 20 (rpmbuild, createrepo, yumdownloader)

- a web browser

- an IRC client

- an up-to-date clone of the Flocker repository

Access
~~~~~~

- A readthedocs account (`registration <https://readthedocs.org/accounts/signup/>`__),
  with `maintainer access <https://readthedocs.org/dashboard/flocker/users/>`__ to the Flocker project.

- Ability to change topic in ``#clusterhq``.
  Ensure that you have `+t` next to your nickname in the output of::

     /msg ChanServ access list #clusterhq

  Somebody with ``+f`` can grant access by running::

     /msg ChanServ access add #clusterhq <nickname> +t

- Access to `Google cloud storage`_ using `gsutil`_.

Preparing for a release
-----------------------

#. Choose a version number
   - Releases numbers should be of the form x.y.z eg::

      export VERSION=0.0.3

#. Checkout the branch for the release.

   .. note:: All releases of the x.y series will be made from the releases/flocker-x.y branch.

   - If this is a major or minor release then create the branch for the minor version::

      git checkout -b release/flocker-${VERSION%.*} origin/master
      git push origin --set-upstream release/flocker-${VERSION%.*}

   - If this is a patch release then there will already be a branch::

      git checkout -b release/flocker-${VERSION%.*} origin/release/flocker-"${VERSION%.*}"

#. Update the version number in the downloads in ``docs/gettingstarted/ubuntu-install.sh`` and ``docs/gettingstarted/osx-install.sh``.
#. Ensure the release notes in :file:`NEWS` are up-to-date.
#. Ensure copyright dates in :file:`LICENSE` are up-to-date.
#. Ensure all the tests pass on BuildBot.
   Go to the `BuildBot web status <http://build.clusterhq.com/boxes-flocker>`_ and force a build on the just-created branch.
#. Do the acceptance tests. (https://github.com/ClusterHQ/flocker/issues/315)

Release
-------

#. Change your working directory to be the Flocker release branch checkout.

#. Create (if necessary) and activate the Flocker release virtual environment::

     virtualenv ~/Environments/flocker-release
     . ~/Environments/flocker-release/bin/activate
     pip install --editable .[release]

#. Tag the version being released::

     git tag --annotate "${VERSION}" release/flocker-"${VERSION%.*}"
     git push origin "${VERSION}"

#. Go to the `BuildBot web status <http://build.clusterhq.com/boxes-flocker>`_ and force a build on the tag.

   .. note:: We force a build on the tag as well as the branch because the RPMs built before pushing the tag won't have the right version.
             Also, the RPM upload script currently expects the RPMs to be built from the tag, rather than the branch.

   You force a build on a tag by putting the tag name into the branch box (without any prefix).

#. Build python packages for upload::

     python setup.py bdist_wheel

   Also upload to archive.clusterhq.com::

     gsutil cp -a public-read dist/Flocker-"${VERSION}"-py2-none-any.whl gs://archive.clusterhq.com/downloads/flocker/

#. Upload RPMs::

      admin/upload-rpms "${VERSION}"

#. Build tagged docs at readthedocs.org.

   Go to the readthedocs `dashboard <https://readthedocs.org/dashboard/flocker/versions/>`_.

   #. Enable the version being released.
   #. Set the default version to that version.

   .. note:: The GitHub readthedocs.org webhook feature should ensure that the new version tag appears immediately.
             If it does not appear, you can force readthedocs.org to reload the repository by running
             ``curl -X POST http://readthedocs.org/build/flocker``


Pre-populating RPM Repository
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These steps must be performed from a machine with the ClusterHQ copr repo installed.
You can either use the :doc:`Flocker development enviroment <vagrant>`
or install the copr repo locally by running `curl https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/repo/fedora-20-x86_64/tomprince-hybridlogic-fedora-20-x86_64.repo >/etc/yum.repos.d/hybridlogic.repo`

::

   mkdir repo
   yumdownloader --destdir=repo geard python-characteristic python-eliot python-idna python-netifaces python-service-identity python-treq python-twisted
   createrepo repo
   gsutil cp -a public-read -R repo gs://archive.clusterhq.com/fedora/20/x86_64


::

   mkdir srpm
   yumdownloader --destdir=srpm --source geard python-characteristic python-eliot python-idna python-netifaces python-service-identity python-treq python-twisted
   createrepo srpm
   gsutil cp -a public-read -R srpm gs://archive.clusterhq.com/fedora/20/SRPMS


Announcing Releases
~~~~~~~~~~~~~~~~~~~

- Announcement

  - on the mailing list - https://groups.google.com/forum/#!forum/flocker-users
  - on the blog - https://clusterhq.com/blog/
  - on the IRC channel - #clusterhq on freenode

- Update download links on clusterhq.com
  XXX Arrange to have download links on a page on clusterhq.com somewhere


.. _gsutil: https://developers.google.com/storage/docs/gsutil
.. _wheel: https://pypi.python.org/pypi/wheel
.. _Google cloud storage: https://console.developers.google.com/project/apps~hybridcluster-docker/storage/archive.clusterhq.com/
