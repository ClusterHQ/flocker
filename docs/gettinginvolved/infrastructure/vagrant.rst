Vagrant
=======

There is a :file:`Vagrantfile` in the base of the repository,
that is pre-installed with all of the dependencies required to run flocker.

See the `Vagrant documentation <http://docs.vagrantup.com/v2/>`_ for more details.

Boxes
-----

There are several vagrant boxes.

Development Box (:file:`vagrant/dev`)
   The box is initialized with the yum repositories for ZFS and for dependencies not available in fedora and installs all the dependencies.
   This is the box the :file:`Vagrantfile` in the root of the repository is based on.

Tutorial Box (:file:`vagrant/tutorial`)
   This box is initialized the the yum repositories for ZFS and flocker, and has flocker pre-installed.
   This is the box the :ref:`tutorial <VagrantSetup>` is based on.


.. _build-vagrant-box:

Building
^^^^^^^^

To build one of the above boxes, run the :file:`build` script in the corresponding directory.
This will generate a :file:`flocker-<box>-<version>.box` file.

Upload this file to `Google Cloud Storage <https://console.developers.google.com/project/apps~hybridcluster-docker/storage/clusterhq-vagrant/>`_,
using `gsutil <https://developers.google.com/storage/docs/gsutil?csw=1>`_::

   gsutil cp -a public_read flocker-dev-$(python ../../setup.py --version).box gs://clusterhq-vagrant/

(If you're uploading the tutorial box the image will be ``flocker-tutorial-...`` instead of ``flocker-dev-...``.)

Then add a version on `Vagrant Cloud (flocker-dev) <https://vagrantcloud.com/clusterhq/flocker-dev>`_ or `Vagrant Cloud (flocker-tutorial) <https://vagrantcloud.com/clusterhq/flocker-tutorial>`_ as applicable.
The version on Vagrant Cloud should be the version with ``-`` replaced with ``.``.

Testing
^^^^^^^
It is possible to test this image locally before uploading.
First add the box locally::

   vagrant box add --name clusterhq/flocker-dev flocker-dev-$(python ../../setup.py --version).box

This adds the box with version 0.
Then change ``config.vm.box_version`` to ``= 0`` in the appropriate :file:`Vagrantfile`,
and then destroy and re-upload that vagrant image.

It is also possible to build a vagrant image based on RPMs from a branch.
If you pass a branch name to :file:`build`, then it will use the RPMs from the latest build of that branch on Buildbot.
