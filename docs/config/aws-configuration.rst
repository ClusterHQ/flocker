.. _aws-dataset-backend:

===================================================
Amazon AWS / EBS Block Device Backend Configuration
===================================================

The AWS backend uses EBS volumes as the storage for datasets.
This backend can be used when Flocker dataset agents are run on EC2 instances.
The configuration item to use AWS should look like:

.. code-block:: yaml

   dataset:
       backend: "aws"
       region: "<region slug; for example, us-west-1>"
       zone: "<availability zone slug; for example, us-west-1a>"
       access_key_id: "<AWS API key identifier>"
       secret_access_key: "<Matching AWS API key>"

Make sure that the ``region`` and ``zone`` match each other and that both match the region and zone where the Flocker agent nodes run.
AWS must be able to attach volumes created in that availability zone to your Flocker nodes.

In addition to the mandatory properties shown, there are some optional properties:

.. option:: session_token

   An AWS session token.
   This allows cross-account access.
   It is mainly useful for testing since session tokens only last for a short time.
   See http://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html for more information on when session tokens are required.

.. option:: validate_region

   Boolean indicating whether to validate the supplied region.
   This defaults to True.
   It is set to False for internal testing.

The Amazon AWS / EBS driver maintained by ClusterHQ provides :ref:`storage-profiles`.
The three available profiles are:

* **Gold**: EBS Provisioned IOPS / API named ``io1``.
  Configured for maximum IOPS for its size - 30 IOPS/GB, with a maximum of 20,000 IOPS.
* **Silver**: EBS General Purpose SSD / API named ``gp2``.
* **Bronze**: EBS Magnetic / API named ``standard``.

If no profile is specified, then a bronze volume is created, which is consistent with previous behavior.

.. note::
	After configuration you are subject to the normal performance guarantees that EBS provides.
	For further information, see the `Amazon EBS Product Details <https://aws.amazon.com/ebs/details/>`_.


