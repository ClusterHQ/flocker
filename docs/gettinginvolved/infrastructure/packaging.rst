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
