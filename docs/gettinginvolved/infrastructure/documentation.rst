Documentation Hosting
=====================

Flocker's documentation is hosted on S3, fronted by cloudfront and cloudflare.

S3 Buckets
----------

There are 3 S3 buckets used for documentation.

clusterhq-docs
~~~~~~~~~~~~~~

This bucket hosts our public facing documentation.

It has documentation for all marketing releases.

Configuration
`````````````
It is configured to allow static website hosting, with an index document of ``index.html``.

It has the following bucket policy configured

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

It has logging enabled. (TODO: figure out what configuration we want, or if this should be at a different layer).

There are empty files at `/index.html` and `/en/index.html` that redirect to the latest docuemntation.

.. prompt:: bash $

   gsutil -h x-amz-website-redirect-location:/en/${VERSION} cp - s3://clusterhq-docs/index.html </dev/null
   gsutil -h x-amz-website-redirect-location:/en/${VERSION} cp - s3://clusterhq-docs/en/index.html </dev/null

TODO
````
- Figure out what to do about error pages.
- Do we want content on the redirect page.

clusterhq-staging-docs
~~~~~~~~~~~~~~~~~~~~~~

This bucket is for staging changes to the main ``clusterhq-docs`` bucket.
It is also used as part of the pre-release testing.
It is configured the same as that bucket (with the name changed throughout).

clusterhq-dev-docs
~~~~~~~~~~~~~~~~~~

This bucket has documentation uploaded to it from buildbot.
Buildbot will upload documentation from all builds of release branches or tags here.


Configuration
`````````````

It is not configured to be publicly accessible.

It has a lifecycle rule that deletes all objects older than 14 days.


CloudFront Distributions
------------------------

docs/staging-docs

pointed at s3 website URL
There are two cloudfront distributions, configured the same except for the bucket
pointed to.

Configuration
~~~~~~~~~~~~~
The following settins should be set:

- Origin Domain Name: clusterhq-docs.s3-website-us-east-1.amazonaws.com
- Origin Path:
- Origin ID: clusterhq-docs
- Origin Protocol Policy: HTTP Only
- Alternate Domain Names: docs.clusterhq.com
- Viewer Protocol Policy: HTTPS Only
- Logging: ??

The rest can be left at their defaults.

.. note::

   We can't use an S3 origin, as redirects won't work.

Improvements
~~~~~~~~~~~~

Perhaps we can have two origins, one being S3, and only
point URLs that need redirections to the website backed one.



CloudFlare
----------

`docs.clusterhq.com` and `docs.staging.clusterhq.com` are configured to point a the corresponding cloudfront distributions.
