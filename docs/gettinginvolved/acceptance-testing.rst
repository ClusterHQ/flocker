Acceptance Testing
==================

Flocker includes a number of acceptance tests and a tool for running them.
It is called like this:

.. prompt:: bash $

   admin/run-acceptance-tests <options> [<test-cases>


The :program:`admin/run-acceptance-tests` script has several options:

.. program:: admin/run-acceptance-tests

.. option:: --distribution <distribution>

   Specifies what distirubtion to use on the created nodes.

.. option:: --provider <provider>

   Specifies what provider to use to create the nodes.

.. option:: --flocker-version <version>

   Specifies the version of flocker to install.
   If this isn't specified, the most recent version will be installed.
   If a branch is also specified, the most recent version from that branch will be installed.
   If a branch is not specified, the most recent release will be installed.

   .. note::

      The buildserver merges forward before bulding packages, except on release branches.
      If you want to run the acceptance tests against a branch in development,
      you probably only want to specify the branch.

.. option:: --branch <branch>

   Specifies the branch from which packages are installed.
   If this isn't specified, packages will be installed from the release repository.

.. option:: --buildserver <buildserver>

   Specifies the base URL of the buildserver to install from.
   This is probably only useful when testing changes to the buildserver.

.. option:: --config-file <config-file>

   Specifies a YAML configuration file that contains provider specific configuration.
   See below for the required configuration options.


Vagrant
-------

A configuration file is not required, for the vagrant provider.


You will need a ssh agent running, with access to the insecure vagrant private key:

.. prompt:: bash $

  ssh-add ~/.vagrant.d/insecure_private_key

Ensure that they all pass, with no skips:

.. prompt:: bash $

  admin/run-acceptance-tests --distribution fedora-20 --provider vagrant

Rackspace
---------

To run the acceptance on Rackspace, you need

- a Rackspace account, and the associated API key
- a ssh-key registered with the Rackspace account.

The config file for the Rackspace provider looks like:

.. code-block:: yaml

   rackspace:
     region: <rackspace region, e.g. "iad">
     username: <rackspace username>
     key: <access key>
     keyname: <ssh-key-name>

You will need a ssh agent running, with access to the corresponding private key.

.. prompt:: bash $

  admin/run-acceptance-tests --distribution fedora-20 --provider rackspace --config-file config.yml
