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

Upload this file to `Amazon S3 <https://console.aws.amazon.com/s3/home?region=us-west-2#&bucket=clusterhq-archive&prefix=>`_,
using `gsutil <https://developers.google.com/storage/docs/gsutil?csw=1>`_::

   gsutil cp -a public-read flocker-dev-$(python ../../setup.py --version).box s3://clusterhq-archive/vagrant

If you are uploading the tutorial box the image will be ``flocker-tutorial-...`` instead of ``flocker-dev-...``.
However, the :ref:`release-process` automatically builds and uploads a new tutorial box.

#. For the following step, retrieve the public link:

   - Visit https://console.aws.amazon.com/s3/home?region=us-west-2#&bucket=clusterhq-archive&prefix=vagrant/.
   - Right click and select "Properties".
   - Copy the "Link".

#. :ref:`add-vagrant-box-to-atlas`\ .

.. _add-vagrant-box-to-atlas:

Add a Vagrant Box to Atlas
^^^^^^^^^^^^^^^^^^^^^^^^^^

To add to Atlas, you will need a public link to the relevant Vagrant box.

#. Visit the Atlas page for creating a new version of the `tutorial box <https://atlas.hashicorp.com/clusterhq/boxes/flocker-tutorial/versions/new>`_ or the `development box <https://atlas.hashicorp.com/clusterhq/boxes/flocker-dev/versions/new>`_ as appropriate.

#. Set the "Version" to the relevant version.

   If adding the ``flocker-dev`` box, ensure that the version number increases using the semantic versioning format.
   This usually involves replacing instances of ``-`` and ``+`` with ``.`` and removing any alphanumeric segments.

   No description is needed.

#. Click "Create version" and then "Create new provider".

#. Set the new provider as "``virtualbox``" and set the URL to be the public link to the Vagrant box.

   Click the "Create provider" button.

#. Click the "Edit" button that appears next to the button containing the version.

#. A message should appear, saying "This version hasn't been released. Upon releasing, it will be available to users from Vagrant".

   Click the "Release version" button next to this message.

Testing
^^^^^^^
It is possible to test this image locally before uploading.
The :file:`build` script generates metadata pointing a the locally built file,
which can be used to add the box with the correct version::

   vagrant box add vagrant/dev/flocker-dev.json

Then destroy and re-up that vagrant image.

It is also possible to build a vagrant image based on RPMs from a branch.
If you pass a ``--branch`` argument to :file:`build`, then it will use the RPMs from the latest build of that branch on Buildbot.
