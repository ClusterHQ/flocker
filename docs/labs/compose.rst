.. _labs-compose:

====================
Flocker with Compose
====================

With Flocker as a Docker plugin, and with Compose ``volume-driver`` support, 
you can use Flocker together with Docker Compose.

First, you need to install Flocker and the Flocker Docker Plugin.
You can use our experimental  :ref:`Flocker Installer <labs-installer>` 
to do this.

Then, you need a version of compose that supports Flocker volumes.

Run the following command to do this:

.. prompt:: bash $

    sudo su -
    pip install git+https://github.com/lukemarsden/compose.git@volume_driver

docker-compose.yml
==================

To make use of Flocker volumes with compose, you will need to specify a
``volume_driver`` field in your ``docker-compose.yml`` file.

Here is an example of a simple application that has 2 containers ``web`` and 
``redis``.  Notice how the ``redis`` container has a data volume and has the
``volume_driver`` field set to ``flocker``.

.. code-block:: yaml

    web:
      image: binocarlos/moby-counter
      links:
        - redis:redis
    redis:
      image: redis
      volume_driver: flocker
      volumes:
         - 'demo:/data'

docker-compose up
=================

Once you have a ``docker-compose.yml`` file that has a ``volume_driver`` field,
you can run a ``docker-compose up`` command as you would normally.

.. prompt:: bash $

    docker-compose up -d

Data volume format - standard
=============================

When you use Flocker to manage data volumes with Compose - the format of the 
data volume is slightly different than normal Docker volumes.

For a normal Docker volume - you would provide the ``host path`` and 
``container path`` as a composite value - here is an example:

.. code-block:: yaml

    redis:
      image: redis
      volume_driver: flocker
      volumes:
         - '/var/lib/redis:/data'

In this example ``/var/lib/redis`` is the host path and ``/data`` is the 
container path.

Data volume format - Flocker
============================

For a Flocker managed volume - you still provide the container path but instead
of a host path, you provide a global name for the volume.

Here is the same example as above but in place of ``/var/lib/redis`` we provide
a global name for the volume.

.. code-block:: yaml

    redis:
      image: redis
      volume_driver: flocker
      volumes:
         - 'demo:/data'

In this example - we have asked Flocker for a volume named ``demo``.  Flocker 
will automatically migrate and mount the volume on a host path for you.