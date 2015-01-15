S3 Buckets
----------

- clusterhq-docs

  - Pointed (via cloudflare and cloudfront) at by docs.clusterhq.com
  - Hosts docs for stable version
  - Has redirect from /en/ to / for RTD compat
  - Docs are synced from clusterhq-dev-docs


- clusterhq-staging-docs

  - Pointed at by docs.staging.clusterhq.com
  - Docs are synced from clusterhq-dev-docs
  - Bucket for testing things for clusterhq-docs
  - Has redirect from /en/ to / for RTD compat


- clusterhq-dev-docs

  - Uploaded to from buildbot


TODO: Add error pages.
- Either in s3 or cloudfront


.. code:: json

   {
      "Version": "2008-10-17",
      "Id": "PolicyForPublicAccess",
      "Statement": [{
         "Sid": "1",
         "Effect": "Allow",
         "Principal": "*",
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::clusterhq-staging-docs/\*"
      }]
   }

.. code:: bash

   gsutil -h x-amz-website-redirect-location:/en/${VERSION} setmeta s3://clusterhq-staging-docs/en/index.html
   gsutil -h x-amz-website-redirect-location:/en/${VERSION} setmeta s3://clusterhq-staging-docs/index.html


.. code:: bash

   gsutil -m rsync -d -r s3://clusterhq-dev-docs/${VERSION}/ s3://clusterhq-staging-docs/en/${VERSION}/

CloudFront Distributions
------------------------

docs/staging-docs

pointed at s3 website URL
(can't use s3 URL, as that doesn't handle redirects or index.html)


CloudFlare
----------

pointed at cloudfront
