Packages for Flocker that aren't available in each supported Operating System.

todo: create a new document, link to it, put the following info in it
See the `documentation <../../docs/gettinginvolved/infrastructure/vagrant.rst#boxes>`_ for details.

Package Hosting
===============

Packages are hosted on Google Cloud Storage and Amazon S3

OS X client packages are hosted on Google Cloud Storage. Where?

Fedora and CentOS client and node packages are hosted on Amazon S3. where?
There are different keys holding dev / marketing.

clusterhq-release package
~~~~~~~~~~~~~~~~~~~~~~~~~

This is a meta-package that contains the yum repository definitions for archive.clusterhq.com.

To build and upload the package, go to the relevant OS / release type directory and run the following commands on the Flocker dev machine XXX todo link xxx todo make python, tested script to do this - probably best for now to have a shell script and use ./update::

   rpmbuild --define="_sourcedir ${PWD}" --define="_rpmdir ${PWD}/results" -ba clusterhq-release.spec
   gsutil cp -a public-read results/noarch/$(rpm --query --specfile clusterhq-release.spec --queryformat '%{name}-%{version}-%{release}').noarch.rpm gs://archive.clusterhq.com/fedora/clusterhq-release.fc20.noarch.rpm
