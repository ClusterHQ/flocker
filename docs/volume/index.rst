Volume Manager
==============

Flocker comes with a volume manager, a tool to manage volumes that can be attached to Docker containers.
Of particular note is the ability to push volumes to different machines.


Configuration
*************
Each host in a Flocker cluster has a universally unique identifier (UUID) for its volume manager.
This allows differentiating between locally owned volumes and volumes that are stored locally but are owned by remote hosts.
By default the UUID is stored in ``/etc/flocker/volume.json``.


``flocker-volume``
******************

Currently the only way to control the volume manager is via the ``flocker-volume`` command-line tool.

No functionality has been implemented yet.
