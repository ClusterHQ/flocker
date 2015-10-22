Vagrant
=======

There is a :file:`Vagrantfile` in the base of the repository,
that is pre-installed with all of the dependencies required to run flocker.

See the `Vagrant documentation <http://docs.vagrantup.com/v2/>`_ for more details.

Boxes
-----

There are several vagrant boxes.

Development Box (:file:`vagrant/dev`)
   This CentOS box is initialized with the yum repositories for ZFS.
   This is the box the :file:`Vagrantfile` in the root of the repository is based on.

Tutorial Box (:file:`vagrant/tutorial`)
   This CentOS box is initialized with the yum repositories for ZFS and Flocker, and has Flocker pre-installed.
   This is the box the :ref:`tutorial <vagrant-setup>` is based on.


Building
^^^^^^^^

Buildbot's `flocker-vagrant-tutorial-box` builder builds the tutorial box.
The `flocker-vagrant-dev-box` builder builds the development box on some branches but not others.
The `flocker-vagrant-dev-box` builder can be forced on any branch.

To build one of the above boxes locally,
upgrade VirtualBox and Vagrant to the latest versions,
install the necessary Vagrant plugins and run the :file:`build` script in the corresponding directory:

.. code-block:: sh

   vagrant plugin install vagrant-reload
   vagrant plugin install vagrant-vbguest
   ./build [Flocker version selection options]

If an error occurs similar to ``/sbin/mount.vboxsf: mounting failed with the error: No such device`` try using the known working versions Vagrant 1.7.2 and VirtualBox 4.3.24r98716.

This will generate a :file:`flocker-<box>-<version>.box` file.

Tutorial boxes and metadata for them are published to `Amazon S3 <https://console.aws.amazon.com/s3/home?region=us-west-2#&bucket=clusterhq-archive&prefix=vagrant/>`_ during the :ref:`release-process`.

To publish the latest development box which has been built by BuildBot:

* Merge a branch into ``master`` with changes to the development box,
* Wait for the development box to be built again for the ``master`` branch,
* Check out an up to date ``master`` branch,
* Run ``admin/publish-dev-box``.

This should be done whenever there is a change to the development box.

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

Metadata for Vagrant boxes was hosted on `Atlas <https://atlas.hashicorp.com>`_.

The Vagrant boxes were hosted on Google Cloud Storage.

The development box used to be based on Fedora 20.
