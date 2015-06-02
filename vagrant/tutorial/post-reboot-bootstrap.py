#!/usr/bin/python

# This script builds the base flocker-dev box.

import sys
import os
from subprocess import check_call, check_output
from textwrap import dedent
from urlparse import urljoin

if len(sys.argv) != 4:
    print "Wrong number of arguments."
    raise SystemExit(1)

rpm_version = sys.argv[1]
branch = sys.argv[2]
build_server = sys.argv[3] or 'http://build.clusterhq.com/'

rpm_dist = check_output(['rpm', '-E', '%dist']).strip()

clusterhq_repo_url = (
    'https://s3.amazonaws.com/'
    'clusterhq-archive/'
    'centos/'
    'clusterhq-release%s.noarch.rpm') % (rpm_dist,)
check_call(['yum', 'install', '-y', clusterhq_repo_url])

if branch:
    # If a branch is specified, add a repo pointing at the
    # buildserver repository corresponding to that branch.
    # This repo will be disabled by default.
    with open('/etc/yum.repos.d/clusterhq-build.repo', 'w') as repo:
        result_path = os.path.join('/results/omnibus', branch,
                                   'centos-$releasever')
        base_url = urljoin(build_server, result_path)
        repo.write(dedent(b"""
            [clusterhq-build]
            name=clusterhq-build
            baseurl=%s
            gpgcheck=0
            enabled=0
            """) % (base_url,))
    branch_opt = ['--enablerepo=clusterhq-build']
else:
    branch_opt = []

# The Flocker packages don't explicitly depend on ZFS because it is only
# required when using the ZFS storage driver.  That's exactly what this box
# wants to do.
check_call(['yum', 'install', '-y', 'zfs'])

# If a version is specifed, install that version.
# Otherwise install whatever yum decides.
if rpm_version:
    # The buildserver doesn't build dirty versions,
    # so strip that.
    if rpm_version.endswith('.dirty'):
        rpm_version = rpm_version[:-len('.dirty')]
    package = 'clusterhq-flocker-node-%s' % (rpm_version,)
else:
    package = 'clusterhq-flocker-node'

# Install flocker-node
check_call(['yum', 'install', '-y'] + branch_opt + [package])

# Install ZFS.
check_call(['yum', 'install', '-y', 'zfs'])

# Enable docker.
# We don't need to start it, since when the box is packaged,
# the machine will be reset.
check_call(['systemctl', 'enable', 'docker'])


# Enable firewalld
# Typical deployments will have a firewall enabled, so enable it on vagrant to
# make the environment more realistic.
# We need to unmask it, since the base box has it masked.
check_call(['systemctl', 'unmask', 'firewalld'])
check_call(['systemctl', 'enable', 'firewalld'])
check_call(['systemctl', 'start', 'firewalld'])
# We need to open the firewall for the flocker-control
for service in ['flocker-control-api', 'flocker-control-agent']:
    check_call(['firewall-cmd', '--permanent', '--add-service', service])

# Make it easy to authenticate as root
check_call(['mkdir', '-p', '/root/.ssh'])
check_call(
    ['cp', os.path.expanduser('~vagrant/.ssh/authorized_keys'), '/root/.ssh'])

# Configure GRUB2 to boot kernel with elevator=noop to workaround
# https://clusterhq.atlassian.net/browse/FLOC-235
with open('/etc/default/grub', 'a') as f:
    f.write('GRUB_CMDLINE_LINUX="${GRUB_CMDLINE_LINUX} elevator=noop"\n')

check_call(['grub2-mkconfig', '-o', '/boot/grub2/grub.cfg'])

# Create a ZFS storage pool backed by a normal filesystem file.  This
# is a bad way to configure ZFS for production use but it is
# convenient for a demo in a VM.
check_call(['mkdir', '-p', '/var/opt/flocker'])
check_call(['truncate', '--size', '1G', '/var/opt/flocker/pool-vdev'])
check_call(['zpool', 'create', 'flocker', '/var/opt/flocker/pool-vdev'])

# Move SSH private key into place so ZFS agent can use it until we remove
# SSH completely in FLOC-1665. The Vagrantfile copied it over, and it's
# the same one we already have in root's authorized_keys (see above).
check_call(['mkdir', '/etc/flocker'])
check_call(['chmod', 'u=rwx,g=,o=', '/etc/flocker'])
check_call(["ssh-keygen", "-N", "", "-f", "/etc/flocker/id_rsa_flocker"])
with file("/root/.ssh/authorized_keys", "a") as f:
    f.write(file("/etc/flocker/id_rsa_flocker.pub").read())

# Workaround https://github.com/mitchellh/vagrant/issues/5590
# New version of CentOS have a NetworkManager that is aggresive about
# configuring network devices. Vagrant tells NetworkManager to not
# manage the device it uses for a static IP, but doesn't tell NetworkManger
# that it has done so. Teach NetworkManager to automatically reload the
# configuration.
with file("/etc/NetworkManager/conf.d/auto-reload.conf", "a") as f:
    f.write("""\
# Created by Flocker (https://clusterhq.atlassian.net/browse/FLOC-2052)
# Workaround https://github.com/mitchellh/vagrant/issues/5590
[main]
monitor-connection-files=true
""")
