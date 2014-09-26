#!/usr/bin/python

# This script builds the base flocker-dev box.

import sys
import os
from subprocess import check_call, check_output
from textwrap import dedent

if len(sys.argv) > 3:
    print "Wrong number of arguments."
    raise SystemExit(1)

if len(sys.argv) > 1:
    version = sys.argv[1]
if len(sys.argv) > 2:
    branch = sys.argv[2]

# Make it possible to install flocker-node
rpm_dist = check_output(['rpm', '-E', '%dist']).strip()
zfs_repo_url = (
    'https://s3.amazonaws.com/'
    'archive.zfsonlinux.org/'
    'fedora/zfs-release%s.noarch.rpm') % (rpm_dist,)
check_call(['yum', 'install', '-y',  zfs_repo_url])

clusterhq_repo_url = (
    'https://storage.googleapis.com/'
    'archive.clusterhq.com/'
    'fedora/clusterhq-release%s.noarch.rpm') % (rpm_dist,)
check_call(['yum', 'install', '-y', clusterhq_repo_url])

if branch:
    with open('/etc/yum.repos.d/clusterhq-build.repo', 'w') as repo:
        repo.write(dedent(b"""
            [clusterhq-build]
            name=clusterhq-build
            baseurl=http://build.clusterhq.com/results/fedora/20/x86_64/%s
            gpgcheck=0
            enabled=0
            """) % (branch,))
    branch_opt = ['--enablerepo=clusterhq-build']
else:
    branch_opt = []
if version:
    package = 'flocker-node-%s' % (version,)
else:
    package = 'flocker-node'
check_call(['yum', 'install', '-y'] + branch_opt + [package])

check_call(['systemctl', 'enable', 'docker'])
check_call(['systemctl', 'enable', 'geard'])

# Make it easy to authenticate as root
check_call(['mkdir', '-p', '/root/.ssh'])
check_call(
    ['cp', os.path.expanduser('~vagrant/.ssh/authorized_keys'), '/root/.ssh'])

# Configure GRUB2 to boot kernel with elevator=noop to workaround
# https://github.com/ClusterHQ/flocker/issues/235
with open('/etc/default/grub', 'a') as f:
    f.write('GRUB_CMDLINE_LINUX="${GRUB_CMDLINE_LINUX} elevator=noop"\n')

check_call(['grub2-mkconfig', '-o', '/boot/grub2/grub.cfg'])
# Create a ZFS storage pool backed by a normal filesystem file.  This
# is a bad way to configure ZFS for production use but it is
# convenient for a demo in a VM.
check_call(['mkdir', '-p', '/opt/flocker'])
check_call(['truncate', '--size', '1G', '/opt/flocker/pool-vdev'])
check_call(['zpool', 'create', 'flocker', '/opt/flocker/pool-vdev'])
