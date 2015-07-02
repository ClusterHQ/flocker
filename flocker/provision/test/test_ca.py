# Copyright ClusterHQ Inc. See LICENSE file for details.

"""
Tests for cluster certificate generation.
"""

from unittest import skipUnless

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.procutils import which

from .. import Certificates


class CertificatesGenerateTests(SynchronousTestCase):
    """
    Tests for ``Certificates.generate``.
    """
    @skipUnless(which(b"flocker-ca"), b"flocker-ca not installed (FLOC-2600)")
    def test_generated(self):
        """
        ``Certificates.generate`` generates a certificate authority
        certificate, a control service certificate, a user certificate, and the
        given number of node certificates.
        """
        output = FilePath(self.mktemp())
        output.makedirs()
        Certificates.generate(output, b"some-service", 2)

        self.assertEqual(
            {
                output.child(b"cluster.crt"), output.child(b"cluster.key"),
                output.child(b"control-some-service.crt"),
                output.child(b"control-some-service.key"),
                output.child(b"user.crt"), output.child(b"user.key"),
                output.child(b"node-0.crt"), output.child(b"node-0.key"),
                output.child(b"node-1.crt"), output.child(b"node-1.key"),
            },
            set(output.children()),
        )
