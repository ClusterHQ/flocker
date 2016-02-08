# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Provisioning for acceptance tests.
"""

from ._common import PackageSource, Variants, INode, IProvisioner
from ._install import (
    provision, configure_cluster, reinstall_flocker_from_package_source
)
from ._rackspace import rackspace_provisioner
from ._aws import aws_provisioner
from ._gce import gce_provisioner
from ._ca import Certificates

CLOUD_PROVIDERS = {
    'rackspace': rackspace_provisioner,
    'aws': aws_provisioner,
    'gce': gce_provisioner,
}

__all__ = [
    'PackageSource', 'Variants',
    'INode', 'IProvisioner',
    'provision',
    'CLOUD_PROVIDERS',
    'configure_cluster',
    'Certificates',
    'reinstall_flocker_from_package_source',
]
