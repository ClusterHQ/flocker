# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common.runner``.
"""
from testtools.matchers import FileContains, DirContains

from twisted.internet import reactor

from flocker.testtools.ssh import (
    create_ssh_server
)
from flocker.common.runner import download, upload
from flocker.testtools import AsyncTestCase, random_name


class UploadTests(AsyncTestCase):
    """
    Tests for ``flocker.common.runner.upload``.
    """
    def test_upload_file(self):
        """
        A single file can be uploaded.
        """
        expected_content = random_name(self)
        local_path = self.make_temporary_file()
        local_path.setContent(expected_content)
        return self.assert_upload(
            local_path,
            FileContains(expected_content)
        )

    def test_upload_directory(self):
        """
        A directory can be uploaded recursively.
        """
        local_path = self.make_temporary_directory()
        local_path.child('child1').open('w')
        return self.assert_upload(
            local_path,
            DirContains(["child1"])
        )

    def assert_upload(self, local_path, matcher):
        """
        Assert that the ``local_path`` can be uploaded to and then downloaded
        from a remote SSH server and that the contents are preserved.

        :param FilePath local_path: The local file or directory to upload.
        :param matcher: A ``testtools`` matcher which will be compared to the
            downloaded ``FilePath.path``.
        :returns: A ``Deferred`` that fires when the assertion is complete.
        """
        self.ssh_server = create_ssh_server(
            base_path=self.make_temporary_directory()
        )
        self.addCleanup(self.ssh_server.restore)

        username = u"root"
        host = bytes(self.ssh_server.ip)

        remote_file = self.ssh_server.home.child(random_name(self))

        d = upload(
            reactor=reactor,
            username=username,
            host=host,
            local_path=local_path,
            remote_path=remote_file,
            port=self.ssh_server.port,
            identity_file=self.ssh_server.key_path,
        )

        download_directory = self.make_temporary_directory()
        download_path = download_directory.child('download')

        d.addCallback(
            lambda ignored: download(
                reactor=reactor,
                username=username,
                host=host,
                remote_path=remote_file,
                local_path=download_path,
                port=self.ssh_server.port,
                identity_file=self.ssh_server.key_path,
            )
        )

        def check(ignored):
            self.assertThat(download_path.path, matcher)
        d.addCallback(check)

        return d
