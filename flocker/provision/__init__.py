# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Provisioning for acceptance tests.
"""

from ._common import PackageSource, Variants, INode, IProvisioner
from ._install import provision, configure_cluster
from ._rackspace import rackspace_provisioner
from ._aws import aws_provisioner
from ._ca import Certificates

CLOUD_PROVIDERS = {
    'rackspace': rackspace_provisioner,
    'aws': aws_provisioner,
}

__all__ = [
    'PackageSource', 'Variants',
    'INode', 'IProvisioner',
    'provision',
    'CLOUD_PROVIDERS',
    'configure_cluster',
    'Certificates',
]
