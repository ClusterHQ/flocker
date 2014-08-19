Building RPMs
=============

To build flocker RPMs, run the following commands:

.. code-block:: sh

   python setup.py sdist
   python setup.py generate_spec
   cp dist/Flocker-$(python setup.py --version).tar.gz ~/rpmbuild/SOURCES
   sudo yum-builddep flocker.spec
   rpmbuild -ba flocker.spec

The above commands require the ``rpmdevtools`` and ``yum-utils`` packages installed.

Flocker depends on a number of packages which aren't available in fedora,
or newer versions than are available there.
These packages are available from `our Copr repository <https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/>`_.
To enable yum to find them, put the `repo file <https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/repo/fedora-20-x86_64/tomprince-hybridlogic-fedora-20-x86_64.repo>`_ in :file:`/etc/yum.repos.d/`.
