Release Process
===============

(cribbed partly from twisted's `release process <https://twistedmatrix.com/trac/wiki/ReleaseProcess>`_)

Outcomes
--------

By the end of the release process we will have:

- Tag in version control
- tarball.
- Fedora 20 RPMs for software on the node and client.
- Release on pypi
- Documentation on docs.clusterhq.com or clusterhq.com/docs
- Annoucment on mailing list, blog, IRC (others?)
- Download links on clusterhq.com


Prequesites
-----------

- A pypi account (`registration <https://pypi.python.org/pypi?%3Aaction=register_form>`__),
  with `maintainer access <https://pypi.python.org/pypi?:action=role_form&package_name=flocker>`__ to the flocker package.
  Configure the account in file:`~/.pypirc`::

     [distutils]
     index-servers =
         pypi

     [pypi]
     username: <username>
     password: <password>

  You will also need `twine <https://pypi.python.org/pypi/twine>`_ installed to upload to pypi.

- A readthedocs account (`registration <https://readthedocs.org/accounts/register/>`__),
  with `maintainer access <https://readthedocs.org/dashboard/flocker/users/>`__ to the flocker project.

- Ability to change topic in ``#clusterhq``.
  Ensure that you have `+t` next to your nickname, in the output of::

     /msg ChanServ access list #clusterhq

  Somebody with ``+f`` can grant access, by running::

     /msg ChanServ access add #clusterhq <nickname> +t

- Access to `google cloud storage <https://console.developers.google.com/project/apps~hybridcluster-docker/storage/archive.clusterhq.com/>`,
  using `gsutil <https://developers.google.com/storage/docs/gsutil>`_.

Preparing for a release
-----------------------
1. Checkout the branch for the release.

   - If this is a major or minor release, create the branch for the minor version::

      git checkout -b release/flocker-${VERSION%.*} origin/master
      git push origin --set-upstream release/flocker-${VERSION%.*}

   - If this is a patch release, there will already be a branch::

      git checkout -b release/flocker-${VERSION%.*} origin/release/flocker-${VERSION%.*}

2. Make sure the release notes in :file:`NEWS` are up-to-date.
3. Update appropriate copyright dates as appropriate.
4. Make sure all the tests pass on buildbot.
   Go to the `buildbot <http://build.clusterhq.com/boxes-flocker>`_ and force a build on the just-created branch.
5. Do the acceptance tests. (https://github.com/ClusterHQ/flocker/issues/315)

Release
-------

1. Tag the version being released::

     git tag -a ${VERSION} release/flocker-${VERSION%.*}
     git push origin ${VERSION}

2.  Go to the `buildbot <http://build.clusterhq.com/boxes-flocker>`_ and force a build on the tag.

3. Build python packages and upload to pypi::

     python sdist bdist_wheel
     twine upload dist/Flocker-${VERSION}{.tar.gz,-py2-none-any.whl}

   Also upload to clusterhq.com download site::

     gsutil -a public-read cp dist/Flocker-${VERSION}{.tar.gz,-py2-none-any.whl} gs://archive.clusterhq.com/downloads/flocker/

4. Upload RPMs::

      admin/upload-rpms upload-scratch ${VERSION}

5. Build tagged docs at readthedocs.org.

   Go to the readthedocs `dashboard <https://readthedocs.org/dashboard/flocker/versions/>`_.

    1. Enable the version being released.
    2. Set the default version to that version.


Announcing Releases
-------------------

- Announcement on mailing list, blog, IRC (others?)
- Update download links on clusterhq.com
  XXX We need a page with the download links first.


clusterhq-release package
^^^^^^^^^^^^^^^^^^^^^^^^^

This is a metapackage that contians the yum repository definitions.

::
   rpmbuild -D "_sourcedir ${PWD}" -D "_rpmdir ${PWD}/results" -ba clusterhq-release.spec
   gsutil cp -a public-read results/noarch/clusterhq-release-1-1.fc20.noarch.rpm gs://archive.clusterhq.com/fedora/clusterhq-release.fc20.noarch.rpm



Pre-populating rpm repository
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
