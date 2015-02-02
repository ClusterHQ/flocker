.. _acceptance-testing:

Acceptance Testing
==================

Flocker includes a number of acceptance tests and a tool for running them.
It is called like this:

.. prompt:: bash $

   admin/run-acceptance-tests <options> [<test-cases>]


The :program:`admin/run-acceptance-tests` script has several options:

.. program:: admin/run-acceptance-tests

.. option:: --distribution <distribution>

   Specifies what distribution to use on the created nodes.

.. option:: --provider <provider>

   Specifies what provider to use to create the nodes.

.. option:: --flocker-version <version>

   Specifies the version of flocker to install.
   If this isn't specified, the most recent version will be installed.
   If a branch is also specified, the most recent version from that branch will be installed.
   If a branch is not specified, the most recent release will be installed.

   .. note::

      The build server merges forward before building packages, except on release branches.
      If you want to run the acceptance tests against a branch in development,
      you probably only want to specify the branch.

.. option:: --branch <branch>

   Specifies the branch from which packages are installed.
   If this isn't specified, packages will be installed from the release repository.

.. option:: --buildserver <buildserver>

   Specifies the base URL of the build server to install from.
   This is probably only useful when testing changes to the build server.

.. option:: --config-file <config-file>

   Specifies a YAML configuration file that contains provider specific configuration.
   See below for the required configuration options.
   If the configuration contains a ``metadata`` key,
   the contents will be added as metadata of the created nodes,
   if the provider supports it.


Vagrant
-------

A configuration file is not required for the vagrant provider.

You will need a ssh agent running with access to the insecure vagrant private key:

.. prompt:: bash $

  ssh-add ~/.vagrant.d/insecure_private_key


.. The following step will go away once FLOC-1163 is addressed.

You will also need the tutorial vagrant box BuildBot has created from the release branch.
The URL can be found by examining the "upload-base-box" step of the ``flocker-vagrant-tutorial-box`` builder.
The URL will look like ``http://build.clusterhq.com/results/vagrant/<branch>/flocker-tutorial.json``.

.. prompt:: bash $

   vagrant box add <URL>

Ensure that they all pass, with no skips:

.. prompt:: bash $

  admin/run-acceptance-tests --distribution fedora-20 --provider vagrant

Rackspace
---------

To run the acceptance tests on Rackspace, you need:

- a Rackspace account and the associated API key
- an ssh-key registered with the Rackspace account.

The configuration file for the Rackspace provider looks like:

.. code-block:: yaml

   rackspace:
     region: <rackspace region, e.g. "iad">
     username: <rackspace username>
     key: <access key>
     keyname: <ssh-key-name>
   metadata:
     creator: <your-name>

You will need a ssh agent running with access to the corresponding private key.

.. prompt:: bash $

  admin/run-acceptance-tests --distribution fedora-20 --provider rackspace --config-file config.yml


AWS
---

To run the acceptance tests on AWS, you need:

- a AWS account and the associated API key
- an ssh-key registered with the AWS account.
- a permissive security group

.. code-block:: yaml

   aws:
     region: <aws region, e.g. "us-west-2">
     access_key: <aws access key>
     secret_access_token: <aws secret access token>
     keyname: <ssh-key-name>
     security_groups: ["<permissive security group>"]
   metadata:
     creator: <your-name>

You will need a ssh agent running with access to the corresponding private key.

.. prompt:: bash $

  admin/run-acceptance-tests --distribution fedora-20 --provider aws --config-file config.yml


DigitalOcean
------------

To run the acceptance tests on DigitalOcean, you need:

- a DigitalOcean account,
- a "Legacy API v1" Client ID and API key
  (https://cloud.digitalocean.com/api_access),
- an "API v2" token, which will be used to update the kernel of new droplets,
  (https://cloud.digitalocean.com/settings/applications), and
- an SSH key registered with the DigitalOcean account.
  (https://cloud.digitalocean.com/ssh_keys)

.. code-block:: yaml

   digitalocean:
     client_id: <DigitalOcean API v1 client id>
     api_key: <DigitalOcean API v1 api key>
     token: <DigitalOcean API v2 api token>
     location: <DigitalOcean location slug e.g. lon1, nyc2, or sfo1>
     keyname: <ssh-key-name>
   metadata:
     creator: <your-name>
