Vagrant
=======

There is a :file:`Vagrantfile` in the base of the repository,
that is pre-installed with all of the dependencies required to run flocker.

See the `Vagrant documentation <http://docs.vagrantup.com/v2/>`_ for more details.

Boxes
-----

There are several vagrant boxes.

Development Box (:file:`vagrant/dev`)
   The box is initialized with the yum repositories for ZFS and for dependencies not available in Fedora and installs all the dependencies.
   This is the box the :file:`Vagrantfile` in the root of the repository is based on.

Tutorial Box (:file:`vagrant/tutorial`)
   This box is initialized with the yum repositories for ZFS and Flocker, and has Flocker pre-installed.
   This is the box the :ref:`tutorial <vagrant-setup>` is based on.


Building
^^^^^^^^

To build one of the above boxes, install the necessary Vagrant plugins and run the :file:`build` script in the corresponding directory.

To build the development box, install the necessary Vagrant plugins as follows:

.. code-block:: sh

   vagrant plugin install vagrant-reload
   vagrant plugin install vagrant-vbguest

This will generate a :file:`flocker-<box>-<version>.box` file.

Upload this file to `Google Cloud Storage <https://console.developers.google.com/project/apps~hybridcluster-docker/storage/clusterhq-vagrant/>`_,
using `gsutil <https://developers.google.com/storage/docs/gsutil?csw=1>`_::

   gsutil cp -a public-read flocker-dev-$(python ../../setup.py --version).box gs://clusterhq-vagrant/

(If you're uploading the tutorial box the image will be ``flocker-tutorial-...`` instead of ``flocker-dev-...``.)

#. For the following step, retrieve the public link:

   - Visit https://console.developers.google.com/project/hybridcluster-docker/storage/clusterhq-vagrant/.
   - Right click and copy the "Public link" for the relevant box.

#. To upload a development box do XXX.
   TODO Do this after the vagrant box > S3 branch is merged as it also changes this.
   Note that the tutorial box is uploaded in the release process.

Testing
^^^^^^^

It is possible to test this image locally before uploading.
The :file:`build` script generates metadata pointing a the locally built file,
which can be used to add the box with the correct version::

   vagrant box add vagrant/dev/flocker-dev.json

Then destroy and re-up that vagrant image.

It is also possible to build a vagrant image based on RPMs from a branch.
If you pass a ``--branch`` argument to :file:`build`, then it will use the RPMs from the latest build of that branch on Buildbot.

Legacy
^^^^^^

Old stuff is on Atlas.