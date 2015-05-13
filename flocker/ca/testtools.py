# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Testing utilities for ``flocker.ca``.
"""

from OpenSSL.crypto import X509Extension


def assert_has_extension(test, credential, name, value):
    """
    Assert that the ``X509Extension`` with the matching name from the
    certificate has the given value.

    :param TestCase test: The current test.
    :param FlockerCredential certificate: Credential whose certificate we
        should inspect.
    :param bytes name: The name of the extension.
    :param bytes value: The data encoded in the extension.

    :raises AssertionError: If the extension is not found or has the wrong
        value.
    """
    expected = X509Extension(name, False, value)
    x509 = credential.certificate.original
    for i in range(x509.get_extension_count()):
        extension = x509.get_extension(i)
        if extension.get_short_name() == name:
            test.assertEqual(extension.get_data(), expected.get_data())
            return
    test.fail("Couldn't find extension {}.".format(name))
