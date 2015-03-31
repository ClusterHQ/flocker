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

from ._common import PackageSource, Variants, Kernel

from flocker.cli import configure_ssh

ZFS_REPO = {
    'fedora-20': "https://s3.amazonaws.com/archive.zfsonlinux.org/"
                 "fedora/zfs-release$(rpm -E %dist).noarch.rpm",
    'centos-7': "https://s3.amazonaws.com/archive.zfsonlinux.org/"
                "epel/zfs-release.el7.noarch.rpm",
}

ARCHIVE_BUCKET = 'clusterhq-archive'

CLUSTERHQ_REPO = {
    'fedora-20': "https://s3.amazonaws.com/{archive_bucket}/"
                 "fedora/clusterhq-release$(rpm -E %dist).noarch.rpm".format(
                     archive_bucket=ARCHIVE_BUCKET,
                 ),
    'centos-7': "https://s3.amazonaws.com/{archive_bucket}/"
                "centos/clusterhq-release$(rpm -E %dist).noarch.rpm".format(
                    archive_bucket=ARCHIVE_BUCKET,
                    ),
}


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


def task_test_homebrew(recipe_url):
    return [
        Run(command="brew update"),
        Run(command="brew install {url}".format(url=recipe_url)),
        Run(command="brew test {url}".format(url=recipe_url)),
    ]


def task_install_ssh_key():
    return [
        Sudo.from_args(['cp', '.ssh/authorized_keys',
                       '/root/.ssh/authorized_keys']),
    ]


KOJI_URL_TEMPLATE = (
    'https://kojipkgs.fedoraproject.org/packages/kernel'
    '/{version}/{release}.{distribution}/{architecture}'
    '/kernel-{version}-{release}.{distribution}.{architecture}.rpm'
)


def koji_kernel_url(kernel):
    """
    Return the koji URL for the given kernel version.
    """
    url = KOJI_URL_TEMPLATE.format(
        version=kernel.version,
        release=kernel.release,
        distribution=kernel.distribution,
        architecture=kernel.architecture
    )
    return url


ZFS_COMPATIBLE_KERNEL = Kernel(
    version="3.17.8",
    release="200",
    distribution="fc20",
    architecture="x86_64"
)

DIGITALOCEAN_KERNEL = ZFS_COMPATIBLE_KERNEL

AWS_FEDORA20_KERNEL = ZFS_COMPATIBLE_KERNEL

DIGITALOCEAN_KERNEL_TITLE = (
    "Fedora 20 x64 "
    "vmlinuz-{kernel.version}-{kernel.release}"
    ".{kernel.distribution}.{kernel.architecture}"
).format(kernel=DIGITALOCEAN_KERNEL)


def task_install_digitalocean_kernel():
    """
    Install a specific Fedora kernel version for DigitalOcean.
    """
    url = koji_kernel_url(DIGITALOCEAN_KERNEL)
    return [
        Run.from_args(['yum', 'update', '-y', url]),
    ]


def task_install_aws_fedora20_kernel():
    """
    Upgrade kernel on an AWS hosted Fedora20 virtual machine
    """
    url = koji_kernel_url(AWS_FEDORA20_KERNEL)
    return [
        Run.from_args(['yum', 'update', '-y', url]),
        Comment(comment="# The upgrade doesn't make the new kernel default."),
        Run.from_args(['grubby', '--set-default-index', '0']),
    ]


def task_upgrade_kernel_centos():
    return [
        Run.from_args([
            "yum", "install", "-y", "kernel-devel", "kernel"]),
        # For dkms and ... ?
        Run.from_args([
            "yum", "install", "-y", "epel-release"]),
        Run.from_args(['sync']),
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
                        ['firewall-cmd']]]


def task_enable_flocker_control():
    """
    Enable flocker-control service.
    """
    return [
        Run.from_args(['systemctl', 'enable', 'flocker-control']),
        Run.from_args(['systemctl', 'start', 'flocker-control']),
    ]


def task_open_control_firewall():
    """
    Open the firewall for flocker-control.
    """
    return reduce(list.__add__, [
        configure_firewalld(['--add-service', service])
        for service in ['flocker-control-api', 'flocker-control-agent']
    ])


AGENT_CONFIG = """\
FLOCKER_NODE_NAME = %(node_name)s
FLOCKER_CONTROL_NODE = %(control_node)s
"""


def task_enable_flocker_agent(node_name, control_node):
    """
    Configure and enable flocker-agent.

    :param bytes node_name: The name this node is known by.
    :param bytes control_node: The address of the control agent.
    """
    return [
        Put(
            path='/etc/sysconfig/flocker-agent',
            content=AGENT_CONFIG % {
                'node_name': node_name,
                'control_node': control_node
            },
        ),
        Run.from_args(['systemctl', 'enable', 'flocker-agent']),
        Run.from_args(['systemctl', 'start', 'flocker-agent']),
    ]


def task_create_flocker_pool_file():
    """
    Create a file-back zfs pool for flocker.
    """
    return [
        Run(command='mkdir -p /var/opt/flocker'),
        Run(command='truncate --size 10G /var/opt/flocker/pool-vdev'),
        Run(command='zpool create flocker /var/opt/flocker/pool-vdev'),
    ]


def task_install_flocker(
        distribution=None,
        package_source=PackageSource()):
    """
    Install flocker.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.
    """
    commands = [
        Run(command="yum install -y " + ZFS_REPO[distribution]),
        Run(command="yum install -y " + CLUSTERHQ_REPO[distribution])
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


def task_enable_updates_testing(distribution):
    """
    Enable the distribution's proposed updates repository.

    :param bytes distribution: See func:`task_install_flocker`
    """
    if distribution == 'fedora-20':
        return [
            Run.from_args(['yum', 'install', '-y', 'yum-utils']),
            Run.from_args([
                'yum-config-manager', '--enable', 'updates-testing'])
        ]
    else:
        raise NotImplementedError


def task_enable_docker_head_repository(distribution):
    """
    Enable the distribution's repository containing in-development docker
    builds.

    :param bytes distribution: See func:`task_install_flocker`
    """
    if distribution == 'fedora-20':
        return [
            Run.from_args(['yum', 'install', '-y', 'yum-utils']),
            Run.from_args([
                'yum-config-manager',
                '--add-repo',
                'https://copr.fedoraproject.org/coprs/lsm5/docker-io/repo/fedora-20/lsm5-docker-io-fedora-20.repo',  # noqa
            ])
        ]
    elif distribution == "centos-7":
        return [
            Put(content=dedent("""\
                [virt7-testing]
                name=virt7-testing
                baseurl=http://cbs.centos.org/repos/virt7-testing/x86_64/os/
                enabled=1
                gpgcheck=0
                """),
                path="/etc/yum.repos.d/virt7-testing.repo")
        ]
    else:
        raise NotImplementedError


def task_enable_zfs_testing(distribution):
    """
    Enable the zfs-testing repository.

    :param bytes distribution: See func:`task_install_flocker`
    """
    if distribution in ('fedora-20', 'centos-7'):
        return [
            Run.from_args(['yum', 'install', '-y', 'yum-utils']),
            Run.from_args([
                'yum-config-manager', '--enable', 'zfs-testing'])
        ]
    else:
        raise NotImplementedError


def provision(distribution, package_source, variants):
    """
    Provision the node for running flocker.

    This drives all the common Fedora20 installation steps in:
     * http://doc-dev.clusterhq.com/gettingstarted/installation.html#installing-on-fedora-20 # noqa

    :param bytes address: Address of the node to provision.
    :param bytes username: Username to connect as.
    :param bytes distribution: See func:`task_install_flocker`
    :param PackageSource package_source: See func:`task_install_flocker`
    :param set variants: The set of variant configurations to use when
        provisioning
    """
    commands = []

    if Variants.DISTRO_TESTING in variants:
        commands += task_enable_updates_testing(distribution)
    if Variants.DOCKER_HEAD in variants:
        commands += task_enable_docker_head_repository(distribution)
    if Variants.ZFS_TESTING in variants:
        commands += task_enable_zfs_testing(distribution)

    if distribution in ('fedora-20',):
        commands += task_install_kernel_devel()

    commands += task_install_flocker(package_source=package_source,
                                     distribution=distribution)
    commands += task_enable_docker()
    commands += task_create_flocker_pool_file()
    commands += task_pull_docker_images()
    return commands


def configure_cluster(control_node, agent_nodes):
    """
    Configure flocker-control and flocker-agent on a collection of nodes.

    :param bytes control_node: The address of the control node.
    :param list agent_nodes: List of addresses of agent nodes.
    """
    run(
        username='root',
        address=control_node,
        commands=task_enable_flocker_control(),
    )
    for node in agent_nodes:
        configure_ssh(node, 22)
        run(
            username='root',
            address=node,
            commands=task_enable_flocker_agent(
                node_name=node,
                control_node=control_node,
            ),
        )


def stop_cluster(control_node, agent_nodes):
    """
    Stop flocker-control and flocker-agent on a collection of nodes.

    :param bytes control_node: The address of the control node.
    :param list agent_nodes: List of addresses of agent nodes.
    """
    run(
        username='root',
        address=control_node,
        commands=[
            Run.from_args(['systemctl', 'stop', 'flocker-control']),
        ],
    )
    for node in agent_nodes:
        run(
            username='root',
            address=node,
            commands=[
                Run.from_args(['systemctl', 'stop', 'flocker-agent']),
            ],
        )
