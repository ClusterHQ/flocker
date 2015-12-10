.. _generate-api-docker-plugin:

======================================================================
Generating an API Client Certificate for the Flocker Plugin for Docker
======================================================================

The Flocker plugin for Docker requires access to the Flocker REST API.
To use the plugin, you will need to create an API client certificate and key for a user named ``plugin`` on each node. 
For more information, see the :ref:`generate-api` instructions.

#. Generate an API client certificate for a user named ``plugin``:

   .. prompt:: bash $

      flocker-ca create-api-certificate plugin

#. Upload the :file:`plugin.key` and :file:`plugin.crt` file via a secure communication medium, such as SSH, SCP or SFTP, to the  :file:`/etc/flocker/` folder on each node in your cluster.
   For example:

   .. prompt:: bash $
   
      scp ./plugin.crt root@172.16.255.251:/etc/flocker/plugin.crt
      scp ./plugin.key root@172.16.255.251:/etc/flocker/plugin.key
