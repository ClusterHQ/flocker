Vagrant
=======

There is a :file:`Vagrantfile` in the base of the repository,
that is pre-installed with all of the dependencies required to run flocker.

See the `Vagrant documentation <http://docs.vagrantup.com/v2/>`_ for more details.

Boxes
-----

There are several vagrant boxes.

Development Box (:file:`vagrant/dev`)
   # TODO update this to reference CentOS.
   The box is initialized with the yum repositories for ZFS and for dependencies not available in Fedora and installs all the dependencies.
   This is the box the :file:`Vagrantfile` in the root of the repository is based on.

Tutorial Box (:file:`vagrant/tutorial`)
   This box is initialized with the yum repositories for ZFS and Flocker, and has Flocker pre-installed.
   This is the box the :ref:`tutorial <vagrant-setup>` is based on.


Building
^^^^^^^^

BuildBot builds a tutorial box for each branch, and a development box for each change to ``master``.

To build one of the above boxes locally, install the necessary Vagrant plugins and run the :file:`build` script in the corresponding directory.

To build the development box, install the necessary Vagrant plugins as follows:

.. code-block:: sh

   vagrant plugin install vagrant-reload
   vagrant plugin install vagrant-vbguest

This will generate a :file:`flocker-<box>-<version>.box` file.

Tutorial boxes and metadata for them are published to `Amazon S3 <https://console.aws.amazon.com/s3/home?region=us-west-2#&bucket=clusterhq-archive&prefix=vagrant/`_ during the :ref:`release-process`.

To publish the latest development box which has been built by BuildBot, run ``admin/publish-dev-box``.
This should be done whenever there is a change to the development box.
TODO Change the Vagrantfile to look at S3.
TODO The script should load http://build.clusterhq.com/results/vagrant/master/flocker-dev.json

Testing
^^^^^^^

It is possible to test a box which has been built locally.
The :file:`build` script generates metadata pointing a the locally built file,
which can be used to add the box with the correct version::

   vagrant box add vagrant/dev/flocker-dev.json

Then destroy and re-up that vagrant image.

It is also possible to build a vagrant image based on RPMs from a branch.
If you pass a ``--branch`` argument to :file:`build`, then it will use the RPMs from the latest build of that branch on Buildbot.

Legacy
^^^^^^

Metadata for Vagrant boxes was hosted on `Atlas`_.

The Vagrant boxes were hosted on Google Cloud Storage.

The development box used to be based on Fedora 20.

.. _`Atlas`: https://atlas.hashicorp.com/vagrant
