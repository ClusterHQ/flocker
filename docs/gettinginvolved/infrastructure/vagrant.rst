Vagrant
=======

There is a :file:`Vagrantfile` in the base of the repository,
that is preinstalled with all of the dependencies required to run flocker.

See the `vagrant documentation <http://docs.vagrantup.com/v2/>`_ for more details.

Base Image
----------

The box the above :file:`Vagrantfile` is based on is generated from :file:`vagrant/base/Vagrantfile`.
The box is initialized with the yum repositories for zfs and for dependencies not available in fedora,
and install all the dependencies besides zfs.

To build the box, run the following commands in the :file:`vagrant/base` directory::

   vagrant up
   vagrant package --output flocker-dev-$(python ../../setup.py --version).box
   vagrant destroy

This will generate a :file:`package-<version>.box`.

Upload this file to `google cloud storage <https://console.developers.google.com/project/apps~hybridcluster-docker/storage/clusterhq-vagrant/>`_,
using `gsutil <https://developers.google.com/storage/docs/gsutil?csw=1>`_::

   gsutil cp -a public_read flocker-dev-$(python ../../setup.py --version).box gs://clusterhq-vagrant/

Then add a version on `vagrantcloud <https://vagrantcloud.com/clusterhq/flocker-dev>`_.
The version on vagrantcloud should be the version with ``-`` replaced with ``.``.

Testing
^^^^^^^
It is possible to test this image locally before uploading.
First add the box locally::

   vagrant box add --name clusterhq/flocker-dev flocker-dev-$(python ../../setup.py --version).box

This adds the box with version 0.
Then change ``config.vm.box_version`` to ``= 0`` in the :file:`Vagrantfile` in the base of the repository,
and then destroy and re-up that vagrant image.
