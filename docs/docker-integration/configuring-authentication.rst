.. _authentication-docker:

==================================
Configuring Cluster Authentication
==================================

.. include:: ../installation/configuring-authentication.rst
   :start-after: .. begin-body-config-authentication
   :end-before: .. end-body-config-authentication

To integrate with Docker you will also need to create API client certificates for the Flocker plugin for Docker, as it requires access to the Flocker REST API.
In addition to the :ref:`generate-api-docker` steps, you will also need to complete the instructions in :ref:`generate-api-docker-plugin`.
