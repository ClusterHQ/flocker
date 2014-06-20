Building RPMs
=============

versioning
----------
   RPM versions

.. note::
   If running under vagrant, the result directory can't be a virtualbox fielsystem (i.e. :file:`/vagrant`).

.. code-block:: sh

   python setup.py sdist
   # put dist/*.tar.gz in ~/rpmbuild/SOURCES
   rpmbuild --define $(pyhton setup.py --version) -ba python-flocker.spec
   # rpm in ~/rpmbuild/SRPMS and ~/rpmbuild/RPMS/noarch

In mock:
.. code-block:: sh
   mock --resultdir $RESULTDIR --buildsrpm --spec python-flocker.spec --sources dist --define="$()"
   mockchain -a <copr> -m --define="$()" -r fedora-20-x86_64 *.src.rpm

To build release pacakges ... add the following to the spec file.

::
   %define flocker_version <....>
