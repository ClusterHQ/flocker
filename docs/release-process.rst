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
- Packages of cli for debian-derivatives and OS X.


Prequesites
-----------

- A pypi account (`registration <https://pypi.python.org/pypi?%3Aaction=register_form>`_),
  with `maintainer access<https://pypi.python.org/pypi?:action=role_form&package_name=flocker>` to the flocker package.
  Configure the account in file:`~/.pypirc`::

     [distutils]
     index-servers =
         pypi

     [pypi]
     username: <username>
     password: <password>

- A readthedocs account (`registration <https://readthedocs.org/accounts/register/>`_),
  with `maintainer access<https://readthedocs.org/dashboard/flocker/users/>`_ to the flocker project.

Preparing for a release
-----------------------
1. Create a branch for the release::

      git checkout -b flocker-$VERSION origin/master
      git push origin --set-upstream flocker-$VERSION

2. Make sure the release notes in :file:`NEWS` are up-to-date.
3. Update appropriate copyright dates as appropriate.
4. Make sure all the tests pass on buildbot.
   Go to the `buildbot<http://build.clusterhq.com/boxes-flocker>`_ and force a build on the just create branch.
   XXX: buildbot needs to not merge forward on release branches
5. Do the acceptance tests.

Release
-------

1. Tag the version being released::

     git tag $VERSION
     git push origin $VERSION

2. Build python packages and upload to pypi::

     python sdist bdist_wheel
     twine upload dist/Flocker-$VERSION{.tar.gz,-py2-none-any.whl}

   Also upload to clusterhq.com dowloand site::

     gsutil -a public-read cp dist/Flocker-$VERSION{.tar.gz,-py2-none-any.whl} gs://archive.clusterhq.com/downloads/flocker/

3. Upload RPMs.

   1. Download existing RPM repo::

         mkdir repo
         gsutil cp -R gs://archive.clusterhq.com/fedora/20/x86_64/ repo

   2. Download release RPMs::

         cat > flocker-$VERSION.repo <<EOF
         [flocker-$VERSION]
         name=flocker-$VERSION
         baseurl=http://build.clusterhq.com/results/fedora/20/x86_64/flocker-$VERSION/
         EOF
         yumdownloader -c flocker-$VERSION.repo --disablerepo='*' --enablerepo=flocker-$VERSION --destdir=repo python-flocker flocker-cli flocker-node

   3. Create repository data::

         createrepo repo

   4. Upload::

         gsutil cp -R -a public-read repo/ gs://archive.clusterhq.com/fedora/20/x86_64/

4. Build tagged docs at readthedocs.org.

   Go to the readthedocs `dashboard <https://readthedocs.org/dashboard/flocker/versions/>`_.

    1. Enable the version being released.
    2. Set the default version to that version.


Stuff do once we have users
---------------------------
Do prereleases

GPG Signing Key?




Stuff needed to get ready for initial release
---------------------------------------------


1. ``INSTALL`` file: installing from git, from tarball, for pypi, from RPM?
