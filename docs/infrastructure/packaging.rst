Building RPMs
=============

To build flocker RPMs, run the following commands:

.. code-block:: sh

   python setup.py sdist
   python setup.py generate_spec
   cp dist/Flocker-$(python setup.py --version).tar.gz ~/rpmbuild/SOURCES
   rpmbuild -ba flocker.spec
