Documentation Hosting
=====================

Flocker's documentation is hosted on S3, fronted by CloudFront.

S3 Buckets
----------

There are 3 S3 buckets used for documentation.

``clusterhq-docs``
~~~~~~~~~~~~~~~~~~

This bucket hosts our public facing documentation.

It has documentation for all marketing releases.

Configuration
`````````````
It is configured to allow static website hosting, with an index document of ``index.html`` and an error document of ``404.html``.

To allow deep-linking to the latest documentation, a redirect configuration is specified.
The following configuration is a sample configuration, with versions current as of 2015-02-03.
Replace the versions for the latest marketing and development releases, and add sections for obsolete version.
The latest marketing and development releases are redirected with temporary redirects to the most recent version;
obsolete releases that are no longer hosted are permanently redirected to the latest version.

.. code:: xml

   <RoutingRules>
     <!-- Marketing Release Documentation -->
     <RoutingRule>
       <Condition>
         <KeyPrefixEquals>en/latest</KeyPrefixEquals>
       </Condition>
       <Redirect>
         <HostName>docs.clusterhq.com</HostName>
         <Protocol>https</Protocol>
         <ReplaceKeyPrefixWith>en/0.3.2/</ReplaceKeyPrefixWith>
         <HttpRedirectCode>302</HttpRedirectCode>
       </Redirect>
     </RoutingRule>
     <!-- Development Release Documentation -->
     <RoutingRule>
       <Condition>
         <KeyPrefixEquals>en/devel</KeyPrefixEquals>
       </Condition>
       <Redirect>
         <HostName>docs.clusterhq.com</HostName>
         <Protocol>https</Protocol>
         <ReplaceKeyPrefixWith>en/0.3.3dev3/</ReplaceKeyPrefixWith>
         <HttpRedirectCode>302</HttpRedirectCode>
       </Redirect>
     </RoutingRule>
     <!-- Obsolete Release Documentation -->
     <RoutingRule>
       <Condition>
         <KeyPrefixEquals>en/0.3.1</KeyPrefixEquals>
       </Condition>
       <Redirect>
         <HostName>docs.clusterhq.com</HostName>
         <Protocol>https</Protocol>
         <ReplaceKeyPrefixWith>en/latest/</ReplaceKeyPrefixWith>
         <HttpRedirectCode>301</HttpRedirectCode>
       </Redirect>
     </RoutingRule>
     <RoutingRule>
       <Condition>
         <KeyPrefixEquals>en/0.3.1.post1</KeyPrefixEquals>
       </Condition>
       <Redirect>
         <HostName>docs.clusterhq.com</HostName>
         <Protocol>https</Protocol>
         <ReplaceKeyPrefixWith>en/latest/</ReplaceKeyPrefixWith>
         <HttpRedirectCode>301</HttpRedirectCode>
       </Redirect>
     </RoutingRule>
     <RoutingRule>
       <Condition>
         <KeyPrefixEquals>en/0.3.0</KeyPrefixEquals>
       </Condition>
       <Redirect>
         <HostName>docs.clusterhq.com</HostName>
         <Protocol>https</Protocol>
         <ReplaceKeyPrefixWith>en/latest/</ReplaceKeyPrefixWith>
         <HttpRedirectCode>301</HttpRedirectCode>
       </Redirect>
     </RoutingRule>
     <!-- For these, we just redirect any possible version, even if they never existed. -->
     <RoutingRule>
       <Condition>
         <KeyPrefixEquals>en/0.2</KeyPrefixEquals>
       </Condition>
       <Redirect>
         <HostName>docs.clusterhq.com</HostName>
         <Protocol>https</Protocol>
         <ReplaceKeyPrefixWith>en/latest/</ReplaceKeyPrefixWith>
         <HttpRedirectCode>301</HttpRedirectCode>
       </Redirect>
     </RoutingRule>
     <RoutingRule>
       <Condition>
         <KeyPrefixEquals>en/0.1</KeyPrefixEquals>
       </Condition>
       <Redirect>
         <HostName>docs.clusterhq.com</HostName>
         <Protocol>https</Protocol>
         <ReplaceKeyPrefixWith>en/latest/</ReplaceKeyPrefixWith>
         <HttpRedirectCode>301</HttpRedirectCode>
       </Redirect>
     </RoutingRule>
     <RoutingRule>
       <Condition>
         <KeyPrefixEquals>en/0.0</KeyPrefixEquals>
       </Condition>
       <Redirect>
         <HostName>docs.clusterhq.com</HostName>
         <Protocol>https</Protocol>
         <ReplaceKeyPrefixWith>en/latest/</ReplaceKeyPrefixWith>
         <HttpRedirectCode>301</HttpRedirectCode>
       </Redirect>
     </RoutingRule>
   </RoutingRules>

To allow CloudFront to access the bucket, it has the following bucket policy configured:

.. code:: json

   {
      "Version": "2008-10-17",
      "Id": "PolicyForPublicAccess",
      "Statement": [{
         "Sid": "1",
         "Effect": "Allow",
         "Principal": "*",
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::clusterhq-docs/*"
      }]
   }


It has logging enabled with the following settings:

- Target Bucket: ``clusterhq-logs.s3.amazonaws.com``
- Target Prefix: ``docs.clusterhq.com/s3/``

There are empty files at ``/index.html`` and ``/en/index.html`` that redirect to the latest documentation.

.. prompt:: bash $

   gsutil -h x-amz-website-redirect-location:/en/${VERSION} cp - s3://clusterhq-docs/index.html </dev/null
   gsutil -h x-amz-website-redirect-location:/en/${VERSION} cp - s3://clusterhq-docs/en/index.html </dev/null

.. TODO - Specify where this is versioned. https://clusterhq.atlassian.net/browse/FLOC-1250

There is an ``error.html`` uploaded to the root of the bucket. It is uploaded with:

.. prompt:: bash /path/to/website/repo $

   gsutil -m cp 404.html s3://clusterhq-docs/404.html


``clusterhq-staging-docs``
~~~~~~~~~~~~~~~~~~~~~~~~~~

This bucket is for staging changes to the main ``clusterhq-docs`` bucket.
It is also used as part of the pre-release testing.

The staging configuration is the same as the production configuration,
with ``docs.staging.clusterhq.com`` replacing ``docs.clusterhq.com`` and ``clusterhq-staging-docs`` replacing ``clusterhq-docs``.

``clusterhq-dev-docs``
~~~~~~~~~~~~~~~~~~~~~~

This bucket has documentation uploaded to it from Buildbot as an intermediate stage to being copied to the above buckets.
Buildbot will upload documentation from all builds of release branches or tags here.
The build will be uploaded to a folded named after the python version
(i.e. the output of ``python setup.py --version``).

Configuration
`````````````

It is not configured to be publicly accessible.

It has a lifecycle rule that deletes all objects older than 14 days.


CloudFront Distributions
------------------------

We use CloudFront to provide SSL in front of the above S3 buckets.
There are 2 CloudFront distributions, one for https://docs.clusterhq.com/ and one for https://docs.staging.clusterhq.com/.
They are pointed at the S3 website URLs (`<bucket-name>.s3-website-us-east-1.awazonaws.com`).

Configuration
~~~~~~~~~~~~~
The configuration of the ``docs.clusterhq.com`` distribution is:

- Origin Domain Name: ``clusterhq-docs.s3-website-us-east-1.amazonaws.com``
- Origin Path:
- Origin ID: ``clusterhq-docs``
- Origin Protocol Policy: HTTP Only
- Alternate Domain Names: ``docs.clusterhq.com``
- Viewer Protocol Policy: HTTPS Only
- Logging: enabled
- Bucket for Logs: ``clusterhq-logs.s3.amazonaws.com``
- Log Prefix: ``docs.clusterhq.com/cloudfront/``
- SSL Certificate: Custom SSL Certificate: ``docs.clusterhq.com``
- Custom SSL Client Support: Only Clients that Support Server Name Indication (SNI)

The rest of the settings can be left at their defaults.
The staging configuration is the same,
with ``docs.staging.clusterhq.com`` replacing ``docs.clusterhq.com`` and ``clusterhq-staging-docs`` replacing `clusterhq-docs``.

.. note::

   We can't use an S3 origin, as redirects won't work.

See the `CloudFront documetation <http://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/SecureConnections.html>`_ for details on uploading SSL key material.
