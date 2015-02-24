# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.provision.test.test_install -*-

"""
Install flocker on a remote node.
"""

from pipes import quote as shell_quote
import posixpath
from textwrap import dedent
from urlparse import urljoin
from characteristic import attributes

from ._common import PackageSource

ZFS_REPO = ("https://s3.amazonaws.com/archive.zfsonlinux.org/"
            "fedora/zfs-release$(rpm -E %dist).noarch.rpm")
CLUSTERHQ_REPO = ("https://storage.googleapis.com/archive.clusterhq.com/"
                  "fedora/clusterhq-release$(rpm -E %dist).noarch.rpm")


@attributes(["command"])
class Run(object):
    """
    Run a shell command on a remote host.

    :param bytes command: The command to run.
    """
    @classmethod
    def from_args(cls, command_args):
        return cls(command=" ".join(map(shell_quote, command_args)))


@attributes(["command"])
class Sudo(object):
    """
    Run a shell command on a remote host.

    :param bytes command: The command to run.
    """
    @classmethod
    def from_args(cls, command_args):
        return cls(command=" ".join(map(shell_quote, command_args)))


@attributes(["content", "path"])
class Put(object):
    """
    Create a file with the given content on a remote host.

    :param bytes content: The desired contests.
    :param bytes path: The remote path to create.
    """


@attributes(["comment"])
class Comment(object):
    """
    Record a comment to be shown in the documentation corresponding to a task.

    :param bytes comment: The desired comment.
    """


def run_with_fabric(username, address, commands):
    """
    Run a series of commands on a remote host.

    :param bytes username: User to connect as.
    :param bytes address: Address to connect to
    :param list commands: List of commands to run.
    """
    from fabric.api import settings, run, put, sudo
    from fabric.network import disconnect_all
    from StringIO import StringIO

    handlers = {
        Run: lambda e: run(e.command),
        Sudo: lambda e: sudo(e.command),
        Put: lambda e: put(StringIO(e.content), e.path),
        Comment: lambda e: None,
    }

    host_string = "%s@%s" % (username, address)
    with settings(
            connection_attempts=24,
            timeout=5,
            pty=False,
            host_string=host_string):

        for command in commands:
            handlers[type(command)](command)
    disconnect_all()


run = run_with_fabric


def task_install_ssh_key():
    return [
        Sudo.from_args(['cp', '.ssh/authorized_keys',
                       '/root/.ssh/authorized_keys']),
    ]


def task_upgrade_kernel():
    """
    Upgrade kernel.
    """
    return [
        Run.from_args(['yum', 'upgrade', '-y', 'kernel']),
        Comment(comment="# The upgrade doesn't make the new kernel default."),
        Run.from_args(['grubby', '--set-default-index', '0']),
    ]


def task_install_kernel_devel():
    """
    Install development headers corresponding to running kernel.

    This is so we can compile zfs.
    """
    return [Run(command="""
UNAME_R=$(uname -r)
PV=${UNAME_R%.*}
KV=${PV%%-*}
SV=${PV##*-}
ARCH=$(uname -m)
yum install -y https://kojipkgs.fedoraproject.org/packages/kernel/\
${KV}/${SV}/${ARCH}/kernel-devel-${UNAME_R}.rpm
""")]


def task_enable_docker():
    """
    Start docker and configure it to start automatically.
    """
    return [
        Run(command="systemctl enable docker.service"),
        Run(command="systemctl start docker.service"),
    ]


def configure_firewalld(rule):
    """
    Configure firewalld with a given rule.

    :param list rule: List of `firewall-cmd` arguments.
    """
    return [
        Run.from_args(command + rule)
        for command in [['firewall-cmd', '--permanent'],
                        ['firewall-cmd']]
    ]


def task_disable_firewall():
    """
    Disable the firewall.
    """
    return configure_firewalld(
        ['--direct', '--add-rule', 'ipv4', 'filter',
         'FORWARD', '0', '-j', 'ACCEPT'])


def task_open_control_firewall():
    """
    Open the firewall for flocker-control.
    """
    return reduce(list.__add__, [
        configure_firewalld(['--add-service', service])
        for service in ['flocker-control-api', 'flocker-control-agent']
    ])


def task_create_flocker_pool_file():
    """
    Create a file-back zfs pool for flocker.
    """
    return [
        Run(command='mkdir -p /var/opt/flocker'),
        Run(command='truncate --size 10G /var/opt/flocker/pool-vdev'),
        Run(command='zpool create flocker /var/opt/flocker/pool-vdev'),
    ]


def task_install_flocker(package_source=PackageSource(),
                         distribution=None):
    """
    Install flocker.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.
    """
    commands = [
        Run(command="yum install -y " + ZFS_REPO),
        Run(command="yum install -y " + CLUSTERHQ_REPO)
    ]

    if package_source.branch:
        result_path = posixpath.join(
            '/results/omnibus/', package_source.branch, distribution)
        base_url = urljoin(package_source.build_server, result_path)
        repo = dedent(b"""\
            [clusterhq-build]
            name=clusterhq-build
            baseurl=%s
            gpgcheck=0
            enabled=0
            """) % (base_url,)
        commands.append(Put(content=repo,
                            path='/etc/yum.repos.d/clusterhq-build.repo'))
        branch_opt = ['--enablerepo=clusterhq-build']
    else:
        branch_opt = []

    if package_source.os_version:
        package = 'clusterhq-flocker-node-%s' % (package_source.os_version,)
    else:
        package = 'clusterhq-flocker-node'

    commands.append(Run.from_args(
        ["yum", "install"] + branch_opt + ["-y", package]))

    return commands


def task_upgrade_selinux():
    return [
        Run.from_args(['yum', 'upgrade', '-y', 'selinux-policy']),
    ]


ACCEPTANCE_IMAGES = [
    "clusterhq/elasticsearch",
    "clusterhq/logstash",
    "clusterhq/kibana",
    "postgres:latest",
    "clusterhq/mongodb:latest",
]


def task_pull_docker_images(images=ACCEPTANCE_IMAGES):
    """
    Pull docker images.

    :param list images: List of images to pull. Defaults to images used in
        acceptance tests.
    """
    return [Run.from_args(['docker', 'pull', image]) for image in images]


def provision(distribution, package_source):
    """
    Provision the node for running flocker.

    :param bytes address: Address of the node to provision.
    :param bytes username: Username to connect as.
    :param bytes distribution: See func:`task_install`
    :param PackageSource package_source: See func:`task_install`
    """
    commands = []
    commands += task_install_kernel_devel()
    commands += task_install_flocker(package_source=package_source,
                                     distribution=distribution)
    commands += task_enable_docker()
    commands += task_create_flocker_pool_file()
    commands += task_pull_docker_images()
    return commands
