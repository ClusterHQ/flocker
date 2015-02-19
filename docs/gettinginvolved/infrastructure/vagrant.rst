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

To build one of the above boxes, run the :file:`build` script in the corresponding directory.
This will generate a :file:`flocker-<box>-<version>.box` file.

Upload this file to `Google Cloud Storage <https://console.developers.google.com/project/apps~hybridcluster-docker/storage/clusterhq-vagrant/>`_,
using `gsutil <https://developers.google.com/storage/docs/gsutil?csw=1>`_::

   gsutil cp -a public-read flocker-dev-$(python ../../setup.py --version).box gs://clusterhq-vagrant/

(If you're uploading the tutorial box the image will be ``flocker-tutorial-...`` instead of ``flocker-dev-...``.)

#. For the following step, retrieve the public link:

   - Visit https://console.developers.google.com/project/hybridcluster-docker/storage/clusterhq-vagrant/.
   - Right click and copy the "Public link" for the relevant box.

#. :ref:`add-vagrant-box-to-atlas`\ .

.. _add-vagrant-box-to-atlas:

Add a Vagrant Box to Atlas
^^^^^^^^^^^^^^^^^^^^^^^^^^

To add to Atlas, you will need a public link to the relevant Vagrant box.

#. Visit `Atlas <https://atlas.hashicorp.com/>`_ and sign in.

#. At the top of the page, select "Development", and from the "Boxes" menu on the left, select "``clusterhq/flocker-dev``" or "``clusterhq/flocker-tutorial``" as applicable.

#. In the menu at the left select "Create new version".

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
