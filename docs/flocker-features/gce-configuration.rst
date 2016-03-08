.. _gce-dataset-backend:

=================================================
Google GCE / Persistent Disk Block Device Backend 
=================================================

.. begin-body

The GCE backend uses persistent disk volumes as the storage for datasets.
This backend can be used when Flocker dataset agents are run on GCE instances.
The :file:`agent.yml` configuration file for the GCE backend should contain the following:

.. code-block:: yaml

   dataset:
       backend: "gce"

By default, credentials in GCE are obtained by using the compute engine service account.
This assumes that when the GCE instance was booted, it was given sufficient scope to perform GCE operations.
For more information, see the Google Cloud Platform instructions for `setting the scope of service account access for instances <https://cloud.google.com/compute/docs/authentication#using>`_.

The required scope is ``https://www.googleapis.com/auth/compute``.
In the GCE console this corresponds to the ``Allow API access to all Google Cloud services in the same project`` checkbox when you start an instance.

If you do not want to use the instance scope to authenticate, you can alternatively add service account credentials to the :file:`agent.yml` configuration file.
For more information about the format of that option, see the optional ``credentials`` key below.

There are no mandatory properties for GCE, but there are some optional properties:

.. option:: project

   The GCE project that the backend should execute operations within.
   In general, this should be the same as the project that the instance running the code is in.
   For that reason, if it is unspecified it defaults to the project as returned from the `GCE Metadata server <https://cloud.google.com/compute/docs/metadata>`_.

   This is sometimes specified for testing purposes when a driver is being constructed on a node that is not on GCE.

.. option:: zone

   The GCE zone (such as ``us-central1-f``) that the backend should execute operations within.
   In general, this should be the same as the zone that the instance running the code is in.
   For that reason, if it is unspecified it defaults to the zone as returned from the `GCE Metadata server <https://cloud.google.com/compute/docs/metadata>`_.

   This is sometimes specified for testing purposes when a driver is being constructed on a node that is not on GCE.

.. option:: credentials

   If the credentials parameter is specified, then the GCE driver will use the given service account credentials rather than the instance's compute engine credentials and scope to authenticate with GCE.

   This requires that you create a separate `OAuth Service Account <https://developers.google.com/identity/protocols/OAuth2ServiceAccount>`_.
   When you create a service account in the GCE console, you are prompted to download a JSON blob with your credentials.
   This option should have precisely the content of that JSON blob.
   For convenience, since JSON is valid YAML, you can copy the contents of the file directly into your YAML configuration.

When running flocker acceptance tests you are required to include all of the optional properties. An example of a fully specified GCE backend configuration looks like:

.. code-block:: yaml

   dataset:
       backend: "gce"
       zone: "us-central1-b"
       project: "example-project"
       # JSON credentials blob downloaded from GCE console. Do not create by hand.
       credentials: {
         "type": "service_account",
         "project_id": "example-project",
         "private_key_id": "1111111111111122222222222223333333333333",
         "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abc...",
         "client_email": "<service-account-name>@example-project.iam.gserviceaccount.com",
         "client_id": "999999998888888887777",
         "auth_uri": "https://accounts.google.com/o/oauth2/auth",
         "token_uri": "https://accounts.google.com/o/oauth2/token",
         "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
         "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/<service-account-name>%40example-project.iam.gserviceaccount.com"
       }

The Google GCE / Persistent disk driver maintained by ClusterHQ provides :ref:`storage-profiles`.
The three available profiles are:

* **Gold**: SSD Persistent Disk
* **Silver**: SSD Persistent Disk
* **Bronze**: Standard Persistent Disk

GCE only provides two different levels of performance, so Gold and Silver have the same level of performance when using the GCE driver.

If no profile is specified, then a bronze volume is created. 

.. note::
	After configuration you are subject to the normal performance guarantees that GCE provides.
	For further information, see the `GCE Block Storage Documentation <https://cloud.google.com/compute/docs/disks/>`_.

.. end-body
