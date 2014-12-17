# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Install flocker on a remote node.
"""

from pipes import quote as shell_quote
import posixpath
from textwrap import dedent
from urlparse import urljoin

from . import PackageSource

ZFS_REPO = ("https://s3.amazonaws.com/archive.zfsonlinux.org/"
            "fedora/zfs-release$(rpm -E %dist).noarch.rpm")
CLUSTERHQ_REPO = ("https://storage.googleapis.com/archive.clusterhq.com/"
                  "fedora/clusterhq-release$(rpm -E %dist).noarch.rpm")


class FabricRunner(object):
    """
    Wrapper around fabric, to make removing it easier.
    """
    def __init__(self, username, address):
        """
        :param username: User to connect as.
        :param address: Address to connect to.
        """
        self.host_string = "%s@%s" % (username, address)

    def _run_in_context(self, f, *args, **kwargs):
        """
        Run a function with fabric environment populated.
        """
        from fabric.api import settings
        with settings(
                connection_attempts=24,
                timeout=5,
                pty=False,
                host_string=self.host_string):
            f(*args, **kwargs)

    def run(self, command):
        """
        Run a shell command on a remote host.

        :param bytes command: The command to run.
        """
        from fabric.api import run
        self._run_in_context(run, command)

    def put(self, content, path):
        """
        Create a file with the given content on a remote host.

        :param bytes content: The desired contests.
        :param bytes path: The remote path to create.
        """
        from fabric.api import put
        from StringIO import StringIO
        self._run_in_context(put, StringIO(content), path)

    def disconnect():
        """
        Disconnect from the remote host.
        """
        from fabric.network import disconnect_all
        disconnect_all()


def task_install_kernel(runner):
    runner.run("""
UNAME_R=$(uname -r)
PV=${UNAME_R%.*}
KV=${PV%%-*}
SV=${PV##*-}
ARCH=$(uname -m)
yum install -y https://kojipkgs.fedoraproject.org/packages/kernel/\
${KV}/${SV}/${ARCH}/kernel-devel-${UNAME_R}.rpm
""")


def task_enable_docker(runner):
    """
    Start docker and configure it to start automatically.
    """
    runner.run("systemctl enable docker.service")
    runner.run("systemctl start docker.service")


def task_disable_firewall(runner):
    """
    Disable the firewall.
    """
    runner.run('firewall-cmd --permanent --direct --add-rule ipv4 filter FORWARD 0 -j ACCEPT')  # noqa
    runner.run('firewall-cmd --direct --add-rule ipv4 filter FORWARD 0 -j ACCEPT')  # noqa


def task_create_flocker_pool_file(runner):
    """
    Create a file-back zfs pool for flocker.
    """
    runner.run('mkdir -p /var/opt/flocker')
    runner.run('truncate --size 10G /var/opt/flocker/pool-vdev')
    runner.run('zpool create flocker /var/opt/flocker/pool-vdev')


def task_install_flocker(runner, package_source=PackageSource(),
                         distribution=None):
    """
    Install flocker.

    :param str distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.
    """
    runner.run("yum install -y " + ZFS_REPO)
    runner.run("yum install -y " + CLUSTERHQ_REPO)

    if package_source.branch:
        result_path = posixpath.join(
            '/results/omnibus/', package_source.branch, distribution)
        base_url = urljoin(package_source.build_server, result_path)
        repo = dedent(b"""
            [clusterhq-build]
            name=clusterhq-build
            baseurl=%s
            gpgcheck=0
            enabled=0
            """) % (base_url,)
        runner.put(repo, '/etc/yum.repos.d/clusterhq-build.repo')
        branch_opt = ['--enablerepo=clusterhq-build']
    else:
        branch_opt = []

    if package_source.version:
        # FIXME flocker -> admin dependency
        from admin.release import make_rpm_version
        rpm_version = "%s-%s" % make_rpm_version(package_source.version)
        if rpm_version.endswith('.dirty'):
            rpm_version = rpm_version[:-len('.dirty')]
        package = 'clusterhq-flocker-node-%s' % (rpm_version,)
    else:
        package = 'clusterhq-flocker-node'

    command = ["yum", "install"] + branch_opt + ["-y", package]
    runner.run(" ".join(map(shell_quote, command)))


def provision(node, username, distribution, package_source):
    """
    Provison the node for running flocker.

    :param node: Node to provision.
    :param username: Username to connect as.
    :param distribution: See func:`task_install`
    :param package_source: See func:`task_install`
    """
    runner = FabricRunner(username, node)

    task_install_kernel(runner)
    task_install_flocker(
        runner,
        package_source=package_source)
    task_enable_docker(runner)
    task_disable_firewall(runner)
    task_create_flocker_pool_file(runner)

    runner.disconnect()
