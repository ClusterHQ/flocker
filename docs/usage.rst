=====
Usage
=====

Flocker manages what containers are running and on what hosts.
It also manages network configuration for these containers (between them and between containers and the world).
And Flocker also creates and replicates volumes.
All of this functionality is available via a simple invocation of the ``flocker-deploy`` program.
This program is included in the Flocker client package.
If you haven't `installed that package`_ yet, you may want to do so now.

Command Line Arguments
======================

``flocker-deploy`` takes just two arguments.
The first of these is the path to a deployment configuration file.
The second is the path to an application configuration file.

.. code-block:: console

    $ flocker-deploy clusterhq_deployment.yml clusterhq_app.yml

The contents of these two configuration files determine what actions Flocker actually takes.
The configuration files completely control this: there are no other command line arguments or options.
See :ref:`configuration` for details about these two files.

You can run ``flocker-deploy`` anywhere you have it installed.
The containers you are managing do not need to be running on the same host as ``flocker-deploy`` is run.

Authentication
==============

Setup
-----

``flocker-deploy`` lets you manage containers on one or more hosts.
Before ``flocker-deploy`` can do this it needs to be able to authenticate itself to these hosts.
Flocker uses SSH to communicate with the hosts you specify in the deployment configuration file.
It requires that you configure this in advance.
The recommended configuration is to `generate an SSH key`_ (if you don't already have one):

.. code-block:: console

    $ ssh-keygen

Then add it to your `SSH key agent`_:

.. code-block:: console

    $ ssh-add <path to key file>


Finally add it to the ``authorized_keys`` file of each host you want to manage:

.. code-block:: console

    $ ssh-copy-id -i <path to key file> <hostname>

This will allow ``flocker-deploy`` to connect to these hosts (as long as the key is still available in your key agent).

If you have a different preferred SSH authentication configuration which allows non-interactive SSH authentication you may use this instead.

Other Keys
----------

``flocker-deploy`` will generate an additional SSH key.
This key is deployed to each host you manage with Flocker and and allows the hosts to authenticate to each other.

.. _`installed that package`: TODO: link to our installation documentation
.. _`generate an SSH key`: https://en.wikipedia.org/wiki/Ssh-keygen
.. _`SSH key agent`: https://en.wikipedia.org/wiki/Ssh-agent
