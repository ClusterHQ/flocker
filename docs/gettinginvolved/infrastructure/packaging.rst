Building Omnibus Packages
=========================

Flocker depends on a number of Python packages which aren't available in its supported operating systems,
or newer versions than are available there.
So the ``build-package`` script bundles those packages into the operating system packages.
We refer to these as "Omnibus" packages.

To build omnibus packages, create a VirtualEnv and install Flocker then its release dependencies:

.. prompt:: bash $

   cd /path/to/flocker
   mkvirtualenv flocker-packaging
   pip install --requirement requirements/admin.txt

Then run the following command from a clean checkout of the Flocker repository:

.. prompt:: bash $

   ./admin/build-package --distribution=centos-7 $PWD

The distribution can be any of the supported distributions (see ``./admin/build-package --help`` for a list).
This will generate three packages files in the current working directory. E.g.

* ``clusterhq-python-flocker-0.3.0-0.dev.1.307.gb6d6e9f.dirty.x86_64.rpm``

  This package will install ``Flocker`` (and all its Python dependencies) into ``/opt/flocker``.

* ``clusterhq-flocker-cli-0.3.0-0.dev.1.307.gb6d6e9f.dirty.noarch.rpm``

  This meta-package will install all the dependencies needed to run the Flocker client scripts.

* ``clusterhq-flocker-node-0.3.0-0.dev.1.307.gb6d6e9f.dirty.noarch.rpm``

  This meta-package will install all the dependencies needed to run the Flocker  scripts.
  It will also install symbolic links in ``/usr/sbin`` for all the Flocker node related scripts.


Instructions for Distribution Maintainers
=========================================

Flocker also includes a ``spec`` file for generating RPMs which comply with the CentOS packaging guidelines.

This is provided as a template for prospective maintainers who may wish to include Flocker in their RPM distribution.

To build Flocker RPMs from the ``spec`` file, run the following commands:

.. prompt:: bash $

   python setup.py sdist
   python setup.py generate_spec
   cp dist/Flocker-$(python setup.py --version).tar.gz ~/rpmbuild/SOURCES
   sudo yum-builddep flocker.spec
   rpmbuild -ba flocker.spec

The commands above require the ``rpmdevtools`` and ``yum-utils`` packages installed.

Package Hosting
===============

New packages are hosted on Amazon S3 in directories in the ``clusterhq-archive`` bucket.

CentOS, Ubuntu, and python client packages as well as node packages are hosted on Amazon S3.

``clusterhq-archive``
---------------------

For each distribution, there are ``<distribution>`` and ``<distribution>-testing`` folders.
Each contains sub-folders for the distribution version and architecture, which finally contain package repositories.

To make the entire bucket public, this bucket has the following policy::

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

``clusterhq-release`` package
-----------------------------

RPM-based distributions tend to bundle ``yum`` repository definitions in ``*-release`` packages.

There are meta-packages which contain the yum repository definitions for `archive.clusterhq.com`.

To build and upload these packages, set up `gsutil` with S3 credentials on a machine with the operating system for which the package is for.
Go to the relevant directory in :file:`admin/release-packaging` and run:

.. prompt:: bash $

   # The basename is the name (not the full path) of the current directory.
   # Package creation files are in directories which match their equivalent S3 keys.
   export S3KEY=$(basename "$PWD")
   rpmbuild --define="_sourcedir ${PWD}" --define="_rpmdir ${PWD}/results" -ba clusterhq-release.spec
   gsutil cp -a public-read results/noarch/$(rpm --query --specfile clusterhq-release.spec --queryformat '%{name}-%{version}-%{release}').noarch.rpm s3://clusterhq-archive/${S3KEY}/clusterhq-release$(rpm -E %dist).noarch.rpm


Legacy
------

Fedora packages were published to Amazon S3 up to but not including version 0.9.0.

Old versions of Flocker for Fedora 20 (until 0.3.2) are hosted on Google Cloud Storage.
The legacy ClusterHQ release package creation files and other packages which were formerly necessary are in https://github.com/ClusterHQ/fedora-packages.

Old versions of Flocker source and binary distributions are hosted on Google Cloud Storage.


Building Docker Images
======================

The Docker images: ``flocker-dataset`` and ``flocker-control`` are built automatically by our CI system.
They are tagged with the Git revision hash and uploaded to https://hub.docker.com/r/clusterhqci.

flocker-dataset-agent
---------------------

To build the Docker image for ``flocker-dataset-agent``, run:

.. prompt:: bash $

   export FLOCKER_VERSION=1.15.0
   docker build \
       --rm \
       --tag "clusterhq/flocker-dataset-agent:${FLOCKER_VERSION}" \
       --build-arg "FLOCKER_VERSION=${FLOCKER_VERSION}-1" \
       dockerfiles/dataset 

You can also build the latest version of Flocker from a custom repository:

.. prompt:: bash $

   docker build \
       --rm \
       --tag "clusterhq/flocker-dataset-agent:master" \
       --build-arg "FLOCKER_REPOSITORY=http://build.clusterhq.com/results/omnibus/master/ubuntu-16.04/" \
       dockerfiles/dataset 

To check the image, run the container with the argument ```--version```:

.. prompt:: bash $

   docker run --rm clusterhq/flocker-dataset-agent:master --version

To run the container:

.. prompt:: bash $

    docker run \
        --net host \
        --privileged \
        --volume /flocker:/flocker:shared \
        --volume /etc/flocker:/etc/flocker:ro \
        --volume /dev:/dev \
        --detach \
        clusterhqci/flocker-dataset-agent:master


flocker-control
---------------

The ``flocker-control`` Docker image is built using the same ```docker build ...``` command line as for ``flocker-dataset`` but substituting the ```control/Dockerfile```.

To run the ``flocker-control`` container:

.. prompt:: bash $

    docker run \
        --name flocker-control \
        --net host \
        -p 4523:4523 \
        -p 4524:4524 \
        --volume /var/lib/flocker:/var/lib/flocker  \
        --volume /etc/flocker:/etc/flocker:ro \
        --detach \
        clusterhqci/flocker-control:master

flocker-docker-plugin
--------------------

The ``flocker-docker-plugin`` Docker image is built using the same ```docker build ...``` command line as for ``flocker-dataset`` but substituting the ```docker-plugin/Dockerfile```.

To run the ``flocker-docker-plugin`` container:

.. prompt:: bash $

    docker run \
        --name flocker-docker-plugin \
        --net host \
        --volume /etc/flocker:/etc/flocker:ro \
        --detach \
        clusterhqci/flocker-docker-plugin:master


