import shutil
import os
from unittest import skipIf

import boto
from effect import Effect, sync_perform, ComposedDispatcher
from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase

from ..aws import boto_dispatcher, UploadToS3
from flocker.provision._effect import dispatcher as base_dispatcher
from flocker.testtools import random_name

# Bucket to use for testing
bucket_name = 'clusterhq-archive-testing'

try:
    boto.connect_s3().head_bucket(bucket_name)
    _can_connect = True
except:
    _can_connect = False

if_aws = skipIf(not _can_connect, "Requires boto AWS credentials")


class AWSTest(SynchronousTestCase):

    @if_aws
    def test_upload_content_type(self):
        """
        A content type can be set for an uploaded file.
        """
        filename = random_name(self)
        tmpdir = FilePath(self.mktemp())
        tmpdir.makedirs()
        tmpfile = tmpdir.child(filename)
        tmpfile.setContent('foo')
        s3 = boto.connect_s3()
        bucket = s3.get_bucket(bucket_name)
        self.addCleanup(bucket.delete_key, filename)
        sync_perform(
            dispatcher=ComposedDispatcher([boto_dispatcher, base_dispatcher]),
            effect=Effect(UploadToS3(
                source_path=tmpdir,
                target_bucket=bucket_name,
                target_key=filename,
                file=tmpfile,
                content_type='application/json',
            ))
        )
        key = bucket.get_key(filename)
        self.assertEqual('application/json', key.content_type)
