Release Process
===============

(cribbed partly from twisted's release process)

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

         yum localinstall http://path.to.repo/flocker-release.fc20.noarch.rmp

      to install flocker.

      We need at least:

      - flocker itself
      - Updated gear package
      - python dependencies
      - zfs packages

  - documentation.
    Options:
    - self-hosted
    - readthedocs.org: Read the docs doesn't support automatically building from new tags.
  - debian/OS X packages


Stuff do once we have users
---------------------------
Do prereleases

GPG Signing Key?




Stuff needed to get ready for initial release
---------------------------------------------


1. ``INSTALL`` file: installing from git, from tarball, for pypi, from RPM?
