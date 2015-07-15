# Copyright ClusterHQ Inc. See LICENSE file for details.
# -*- test-case-name: flocker.provision.test.test_ca -*-

"""
Create certificates for a cluster.
"""

from twisted.python.filepath import FilePath

from subprocess import check_call

from flocker.ca import RootCredential


class CertAndKey(object):
    """
    Paths to a matching pair of certificate and key files.

    :ivar FilePath certificate: Path to the certificate.
    :ivar FilePath key: Path to the private key.
    """
    def __init__(self, certificate, key):
        for path in (certificate, key):
            if not path.exists():
                raise RuntimeError("{} does not exist".format(path))
        self.certificate = certificate
        self.key = key


class Certificates(object):
    """
    The certificates generated for a cluster.

    :ivar FilePath directory: See ``__init__``.
    :ivar CertAndKey cluster: The certificate authority/cluster files.
    :ivar CertAndKey control: The control service files.
    :ivar CertAndKey user: The user files.
    :ivar list nodes: ``list`` of ``CertAndKey`` for nodes.
    """
    def __init__(self, directory):
        """
        :param FilePath directory: Directory where the certificates can be
            found.
        """
        self.directory = directory
        self.cluster = CertAndKey(directory.child(b"cluster.crt"),
                                  directory.child(b"cluster.key"))
        # Assume only one control service:
        self.control = CertAndKey(
            directory.globChildren(b"control-*.crt")[0],
            directory.globChildren(b"control-*.key")[0])
        self.user = CertAndKey(directory.child(b"user.crt"),
                               directory.child(b"user.key"))
        nodes = []
        for child in directory.globChildren(b"node-*.crt"):
            sibling = FilePath(child.path[:-3] + b"key")
            nodes.append(CertAndKey(child, sibling))
        self.nodes = nodes

    @classmethod
    def generate(cls, directory, control_hostname, num_nodes, cluster_id=None):
        """
        Generate certificates in the given directory.

        :param FilePath directory: Directory to use for certificate authority.
        :param bytes control_hostname: The hostname of the control service.
        :param int num_nodes: Number of nodes in the cluster.
        :param UUID cluster_id: The unique identifier of the cluster for which
            the certificates are being generated.  If not given, a random
            identifier will be generated.

        :return: ``Certificates`` instance.
        """
        RootCredential.initialize(
            directory, b"acceptance-cluster", cluster_id=cluster_id,
        )

        def run(*arguments):
            check_call([b"flocker-ca"] + list(arguments), cwd=directory.path)

        run(b"create-control-certificate", control_hostname)
        run(b"create-api-certificate", b"allison")
        # Rename to user.crt/user.key so we can use this folder directly
        # from flocker-deploy and other clients:
        directory.child(b"allison.crt").moveTo(directory.child(b"user.crt"))
        directory.child(b"allison.key").moveTo(directory.child(b"user.key"))
        for i in range(num_nodes):
            run(b"create-node-certificate")
        for i, child in enumerate(
                directory.globChildren(b"????????-????-*.crt")):
            sibling = FilePath(child.path[:-3] + b"key")
            child.moveTo(directory.child(b"node-%d.crt" % (i,)))
            sibling.moveTo(directory.child(b"node-%d.key" % (i,)))
        return cls(directory)
