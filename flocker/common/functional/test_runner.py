# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common.runner``.
"""
from twisted.internet import reactor
from twisted.python.filepath import FilePath

from flocker.common.runner import download_file, upload
from flocker.testtools import AsyncTestCase, random_name


class UploadTests(AsyncTestCase):
    def test_upload_file(self):
        expected_content = random_name(self)
        username = u"ubuntu"
        host = u"54.193.57.202"

        local_file = self.make_temporary_file()
        local_file.setContent(expected_content)
        remote_file = FilePath('/home/ubuntu').child(random_name(self))

        d = upload(
            reactor=reactor,
            username=username,
            host=host,
            local_path=local_file,
            remote_path=remote_file,
        )

        download_directory = self.make_temporary_directory()
        download_path = download_directory.child('download')

        def download(ignored):
            return download_file(
                reactor=reactor,
                username=username,
                host=host,
                remote_path=remote_file,
                local_path=download_path,
            )
        d.addCallback(download)

        def check(ignored):
            self.assertEqual(
                expected_content,
                download_path.getContent()
            )
        d.addBoth(check)

        return d
