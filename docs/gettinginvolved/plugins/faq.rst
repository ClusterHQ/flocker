.. _build-flocker-driver-faq:

===
FAQ
===

Please read through the following frequently asked questions encountered when building and troubleshooting your driver.

.. contents::
    :local:
    :backlinks: none

Driver Development
==================

Is ``dataset_id`` unique for each volume created?
-------------------------------------------------

Yes.

Is there some way to get the ``dataset_id`` from Flocker given the ``blockdevice_id`` specific to our driver?
-------------------------------------------------------------------------------------------------------------

No.

Does the Flocker node agent cache any state?
--------------------------------------------

No.
The only state cached is in the Flocker control agent.

Is there a script to cleanup volumes leftover from running functional tests?
-----------------------------------------------------------------------------

Yes.
After each test case, `detach_destroy_volumes <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/test/test_blockdevice.py>`_ is run automatically to cleanup volumes created by the test case.
This cleanup call is added as part of `get_blockdeviceapi_with_cleanup <https://github.com/ClusterHQ/flocker/blob/master/flocker/node/agents/test/blockdevicefactory.py>`_ .

Please use ``get_blockdeviceapi_with_cleanup`` in your test wrapper.

I get a lot of output in ``journactl`` and it’s very difficult to track what all is happening, is there an easy way to view the logs?
-------------------------------------------------------------------------------------------------------------------------------------

`eliottree` is the preferred way, but it currently does not work due to `a known bug <https://github.com/jonathanj/eliottree/issues/28>`_ . 

Troubleshooting
===============

How do I go about debugging after a functional test has failed?
---------------------------------------------------------------

Start with the Flocker node agent log (:file:`/var/log/flocker/flocker-dataset-agent.log`).
You can use `eliot-tree <https://github.com/jonathanj/eliottree>`_ to render the log in ASCII format. 

Following this, review the storage driver log, then storage backend logs.

How do I triage further if I see the following error in Flocker dataset agent log?
----------------------------------------------------------------------------------

.. prompt:: bash $

   Command '['mount', '/dev/sdb', '/flocker/c39e7d1c-7c9e-6029-4c30-42ab8b44a991']' returned non-zero exit status 32

Please run the failed command from the command line prompt - the cause of failure is most likely environment related (incomplete attach/detach operation preceding the command), and not caused by bug in Flocker or Flocker Storage driver.

What do I do if I see the following error while running acceptance tests?
-------------------------------------------------------------------------

.. prompt:: bash $ auto

   $ /root//flocker/flocker-tutorial/bin//python  /root/f/flocker/admin/run-acceptance-tests -—provider=managed  —-distribution=centos-7 -—config-file=/etc/flocker/acceptancetests.yml
   Generating certificates in: /tmp/tmp24HnaK
   Created control-172.22.21.75.crt and control-172.22.21.75.key
   Copy these files to the directory /etc/flocker on your control service machine.
   Rename the files to control-service.crt and control-service.key and set the correct permissions by running chmod 0600 on both files.
   Created allison.crt. You can now give it to your API enduser so they can access the control service API.
   Created 40d78681-5755-48c6-8e28-c36bf5a485c5.crt. Copy it over to /etc/flocker/node.crt on your node machine and sure to chmod 0600 it.
   Created 03e53f5a-894f-44e4-8296-0c319a689179.crt. Copy it over to /etc/flocker/node.crt on your node machine and sure to chmod 0600 it.

Please check that you have configured Flocker CA certs as documented :ref:`here <authentication>`.

How do I reset the Flocker control service state if my test environment is messed up? 
-------------------------------------------------------------------------------------

Flocker control state is stored in :file:`/var/lib/flocker/current_configuration.v1.json` on the control compute node.
You can remove the file to reset the Flocker control service state:


.. prompt:: bash $

	systemctl stop flocker-control
	rm /var/lib/flocker/current_configuration.v1.json
	systemctl start flocker-control
