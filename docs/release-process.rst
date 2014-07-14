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



Preparing for a release
-----------------------
- Branch for release: ``flocker-$VERSION``.
- Relase notes: ``NEWS``
  - Check that release notes are up-to-date for new features
  - Make sure all incompatible changes and deprecations are documented
- Make sure all tests pass.
- Update appropriate copyright dates (years?)
- Review?
- Acceptance testing (manual and automatic)

Release
-------
- Tag release
- Build and publish:
  - sdist::

      python sdist bdist_wheel
      twine upload dist dist/Flocker-$VERSION*.{tar.gz,whl}

    Also upload to clusterhq.com dowloand site.

  - RPMs

    - We probably want our users to only point there machine a single repository.
      That means we also need to include all the dependencies that aren't upstream, or at least automatically add them.
      We should build a package that points at the appropriate repository, so they can do::

         yum localinstall http://path.to.repo/flocker-release.fc20.noarch.rpm

      to install flocker.

      We need at least:

      - flocker itself
      - Updated gear package
      - python dependencies
      - zfs packages

  - documentation.
    Options:
    - self-hosted

      - get buildbot to upload somewhere (either a tarball that can be extracted somewhere, or directly live).

    - readthedocs.org: Read the docs doesn't support automatically building from new tags.

      - Click the checkbox on the readthedocs `https://readthedocs.org/dashboard/flocker/versions/ <dashboard>`_.

  - debian/OS X packages

    Perhaps for 0.1 we just want to suggest people do `pip install`?
    If we do this, we should probably move the private scripts behind an extra flag.


Stuff do once we have users
---------------------------
Do prereleases

GPG Signing Key?




Stuff needed to get ready for initial release
---------------------------------------------


1. ``INSTALL`` file: installing from git, from tarball, for pypi, from RPM?
