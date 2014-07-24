Release Process
===============

Outcomes
--------

By the end of the release process we will have:

- a tag in version control
- a Python wheel on archive.clusterhq.com
- Fedora 20 RPMs for software on the node and client
- documentation on clusterhq.com/docs
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

- A readthedocs account (`registration <https://readthedocs.org/accounts/register/>`__),
  with `maintainer access <https://readthedocs.org/dashboard/flocker/users/>`__ to the Flocker project.

- Ability to change topic in ``#clusterhq``.
  Ensure that you have `+t` next to your nickname in the output of::

     /msg ChanServ access list #clusterhq

  Somebody with ``+f`` can grant access by running::

     /msg ChanServ access add #clusterhq <nickname> +t

- Access to `Google cloud storage`_ using `gsutil`_.

Preparing for a release
-----------------------
#. Checkout the branch for the release.

   - If this is a major or minor release then create the branch for the minor version::

      git checkout -b release/flocker-${VERSION%.*} origin/master
      git push origin --set-upstream release/flocker-${VERSION%.*}

   - If this is a patch release then there will already be a branch::

      git checkout -b release/flocker-${VERSION%.*} origin/release/flocker-"${VERSION%.*}"

#. Make sure the release notes in :file:`NEWS` are up-to-date.
#. Update appropriate copyright dates as appropriate.
#. Make sure all the tests pass on BuildBot.
   Go to the `BuildBot web status <http://build.clusterhq.com/boxes-flocker>`_ and force a build on the just-created branch.
#. Do the acceptance tests. (https://github.com/ClusterHQ/flocker/issues/315)

Release
-------

#. Change your working directory to be the Flocker release branch checkout.

#. Create (if necessary) and activate the Flocker release virtual environment::

     virtualenv ~/Environments/flocker-release
     . ~/Environments/flocker-release/bin/activate
     pip install -e .[release]

#. Tag the version being released::

     git tag -a "${VERSION}" release/flocker-"${VERSION%.*}"
     git push origin "${VERSION}"

#. Go to the `BuildBot web status <http://build.clusterhq.com/boxes-flocker>`_ and force a build on the tag.

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


clusterhq-release package
~~~~~~~~~~~~~~~~~~~~~~~~~

This is a meta-package that contains the yum repository definitions.

::

   rpmbuild -D "_sourcedir ${PWD}" -D "_rpmdir ${PWD}/results" -ba clusterhq-release.spec
   gsutil cp -a public-read results/noarch/clusterhq-release-1-1.fc20.noarch.rpm gs://archive.clusterhq.com/fedora/clusterhq-release.fc20.noarch.rpm


Pre-populating rpm repository
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

with copr repo installed

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
