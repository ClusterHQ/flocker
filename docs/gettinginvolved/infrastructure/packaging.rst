Building RPMs
=============

To build flocker RPMs, run the following command from a clean checkout of the Flocker repository:

.. code-block:: sh

   admin/build-package .

This will generate a ``Flocker-X.Y.Z-*.rpm`` package file.
The package will install ``Flocker`` (and all its dependencies) into ``/opt/flocker`` and add all the Flocker command line scripts to the system path.

.. note:: The ``build-package`` command requires the ``fpm`` tool to be installed.

Dependencies
------------

Flocker depends on a number of packages which aren't available in fedora,
or newer versions than are available there.
So the ``build-package`` script bundles those packages into the RPM.
We refer to these as "sumo" packages.
Elsewhere they are referred to as "omnibus" packages.
