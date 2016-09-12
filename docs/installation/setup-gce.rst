.. Single Source Instructions

============================================
Setting Up Nodes Using Google Compute Engine
============================================

.. begin-body

You can get a Flocker cluster running using Google Compute Engine.
You'll need to setup at least two nodes.

#. Create a new cloud server:

   * Visit the `Google Cloud Console <https://console.cloud.google.com/>`_.
   * Navigate to the project you want to use.
   * Use the menu in the upper left to navigate to ``Compute Engine``.
   * Click ``Create Instance``.
   * Choose a name and a zone for your instance. Zone must be the same for all instances.
   * Choose a machine type.
   * For the Boot Disk, choose a supported Linux distribution (either RHEL 7, CentOS 7, Ubuntu 16.04 or Ubuntu 14.04) as your image.
   * Under ``Identity and API Access`` select ``Set access for each API`` and grant Read Write access to ``Compute``.
   * Click ``Create`` to create the new instance.

#. Gain SSH Access:

   You can SSH into the machine either using the in-browser SSH client by clicking ``SSH`` on the instances page, or by using the `gcloud <https://cloud.google.com/sdk/gcloud/>`_ command line tool.

   .. prompt:: bash alice@mercury:~$

      gcloud compute --project <project-name> ssh --zone <zone-name> <instance-name>

.. end-body
