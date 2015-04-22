Building Omnibus RPMs
=====================

Flocker depends on a number of Python packages which aren't available in Fedora,
or newer versions than are available there.
So the ``build-package`` script bundles those packages into the RPM.
We refer to these as "Omnibus" packages.

To build omnibus RPMs, create a VirtualEnv and install Flocker then its release dependencies:

.. code-block:: sh

   cd /path/to/flocker
   mkvirtualenv flocker-packaging
   pip install .
   pip install Flocker[release]

Then run the following command from a clean checkout of the Flocker repository:

.. code-block:: sh

   ./admin/build-package --distribution=fedora-20 $PWD

This will generate three RPM files in the current working directory. E.g.

* ``clusterhq-python-flocker-0.3.0-0.dev.1.307.gb6d6e9f.dirty.x86_64.rpm``

  This package will install ``Flocker`` (and all its Python dependencies) into ``/opt/flocker``.

* ``clusterhq-flocker-cli-0.3.0-0.dev.1.307.gb6d6e9f.dirty.noarch.rpm``

  This meta-package will install all the dependencies needed to run the Flocker client scripts.
  It will also install a symbolic link for ``flocker-deploy`` in ``/usr/bin``.

* ``clusterhq-flocker-node-0.3.0-0.dev.1.307.gb6d6e9f.dirty.noarch.rpm``

  This meta-package will install all the dependencies needed to run the Flocker  scripts.
  It will also install symbolic links in ``/usr/sbin`` for all the Flocker node related scripts.


Instructions for Distribution Maintainers
=========================================

Flocker also includes a ``spec`` file for generating RPMs which comply with the Fedora packaging guidelines.

This is provided as a template for prospective maintainers who may wish to include Flocker in their RPM distribution.

To build Flocker RPMs from the ``spec`` file, run the following commands:

.. code-block:: sh

   python setup.py sdist
   python setup.py generate_spec
   cp dist/Flocker-$(python setup.py --version).tar.gz ~/rpmbuild/SOURCES
   sudo yum-builddep flocker.spec
   rpmbuild -ba flocker.spec

The commands above require the ``rpmdevtools`` and ``yum-utils`` packages installed.

Flocker depends on a number of packages which aren't available in fedora.
These packages are available from `our Copr repository <https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/>`_.
To enable yum to find them, put the `repo file <https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/repo/fedora-20-x86_64/tomprince-hybridlogic-fedora-20-x86_64.repo>`_ in :file:`/etc/yum.repos.d/`.


Package Hosting
===============

Some packages are hosted on Google Cloud Storage and others are hosted on Amazon S3.

The Homebrew installation script for OS X downloads packages from `Google Cloud Storage <https://console.developers.google.com/project/hybridcluster-docker/storage/browser/archive.clusterhq.com/downloads/flocker/?authuser=1>`_.

Fedora 20 and CentOS client and node packages are hosted on Amazon S3.
These are in the `clusterhq-archive` bucket.
Within this bucket there are `development` and `marketing` keys.
Within each of these are keys for each supported operating system.

`clusterhq-archive`
-------------------

This bucket has the following policy::

   {
   	"Version": "2008-10-17",
   	"Id": "PolicyForPublicAccess",
   	"Statement": [
   		{
   			"Sid": "1",
   			"Effect": "Allow",
   			"Principal": "*",
   			"Action": "s3:GetObject",
   			"Resource": "arn:aws:s3:::clusterhq-archive/*"
   		}
   	]
   }

A policy can be set by going to a bucket's "Properties", "Permissions", then "Add bucket policy".

``clusterhq-dev-archive``
-------------------------

BuildBot puts Vagrant boxes in the ``clusterhq-dev-archive``.
This has a similar policy to the ``clusterhq-archive`` bucket but is more restrictive in that only the keys with the prefix "vagrant/" are public.

This bucket has the following policy::

   {
   	"Version": "2008-10-17",
   	"Id": "PolicyForPublicAccess",
   	"Statement": [
   		{
   			"Sid": "1",
   			"Effect": "Allow",
   			"Principal": "*",
   			"Action": "s3:GetObject",
   			"Resource": "arn:aws:s3:::clusterhq-dev-archive/vagrant/*"
   		}
   	]
   }

`clusterhq-release package`
---------------------------

There are meta-packages which contain the yum repository definitions for `archive.clusterhq.com`.

XXX This should be a Python script with tests which can be run on the :doc:`Flocker development machine <vagrant>` https://clusterhq.atlassian.net/browse/FLOC-1530

To build and upload these packages, on a machine with the operating system which the package is for
(an easy way to do this is to use the :doc:`Flocker development machine <vagrant>` and an old Fedora 20 version of it),
set up `gsutil` with S3 credentials,
go to the relevant directory in `admin/release-packaging` and run:

.. code-block:: sh

   # The basename is the name (not the full path) of the current directory.
   # Package creation files are in directories which match their equivalent S3 keys.
   export S3KEY=$(basename "$PWD")
   rpmbuild --define="_sourcedir ${PWD}" --define="_rpmdir ${PWD}/results" -ba clusterhq-release.spec
   gsutil cp -a public-read results/noarch/$(rpm --query --specfile clusterhq-release.spec --queryformat '%{name}-%{version}-%{release}').noarch.rpm s3://clusterhq-archive/${S3KEY}/clusterhq-release$(rpm -E %dist).noarch.rpm


Legacy
------

Old versions of Flocker for Fedora 20 (until 0.3.2) are hosted on Google Cloud Storage.
The legacy ClusterHQ release package creation files and other packages which were formerly necessary are in https://github.com/ClusterHQ/fedora-packages.
