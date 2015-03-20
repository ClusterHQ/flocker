# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Provisioning for acceptance tests.
"""

from ._common import PackageSource, Variants
from ._install import provision, configure_cluster
from ._rackspace import rackspace_provisioner
from ._aws import aws_provisioner
from ._digitalocean import digitalocean_provisioner

CLOUD_PROVIDERS = {
    'rackspace': rackspace_provisioner,
    'aws': aws_provisioner,
    'digitalocean': digitalocean_provisioner,
}

__all__ = [
    'PackageSource', 'Variants',
    'provision',
    'CLOUD_PROVIDERS',
    'configure_cluster',
]
