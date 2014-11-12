Building Omnibus RPMs
=====================

Flocker depends on a number of Python packages which aren't available in Fedora,
or newer versions than are available there.
So the ``build-package`` script bundles those packages into the RPM.
We refer to these as "Omnibus" packages.

To build omnibus RPMs, run the following command from a clean checkout of the Flocker repository:

.. code-block:: sh

   ./admin/build-package --distribution=fedora20 $PWD

This will generate three RPM files in the current working directory. E.g.

* clusterhq-python-flocker-0.3.0-0.dev.1.307.gb6d6e9f.dirty.x86_64.rpm

  This package will install ``Flocker`` (and all its Python dependencies) into ``/opt/flocker``.

* clusterhq-flocker-cli-0.3.0-0.dev.1.307.gb6d6e9f.dirty.noarch.rpm

  This meta-package will install all the dependencies needed to run the Flocker client scripts.
  It will also install a symlink for ``flocker-deploy`` in ``/usr/sbin``.

* clusterhq-flocker-node-0.3.0-0.dev.1.307.gb6d6e9f.dirty.noarch.rpm

  This meta-package will install all the dependencies needed to run the Flocker  scripts.
  It will also install symlinks in ``/usr/sbin`` for all the Flocker node related scripts.
