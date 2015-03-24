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
from effect import Effect, parallel

from ._common import PackageSource, Variants
from ._ssh import run_with_crochet
from ._effect import sequence

from flocker.cli import configure_ssh
__all__ = ['run_with_crochet']

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


def run(command):
    return Effect(Run(command=command))


def sudo(command):
    return Effect(Sudo(command=command))


def put(content, path):
    return Effect(Put(content=content, path=path))


def comment(comment):
    return Effect(Comment(comment=comment))


def run_from_args(command):
    return Effect(Run.from_args(command))


def sudo_from_args(command):
    return Effect(Sudo.from_args(command))


def task_test_homebrew(recipe_url):
    return sequence([
        run("brew update"),
        run("brew install {url}".format(url=recipe_url)),
        run("brew test {url}".format(url=recipe_url)),
    ])


def task_install_ssh_key():
    return sequence([
        sudo_from_args(['cp', '.ssh/authorized_keys',
                        '/root/.ssh/authorized_keys']),
    ])


def task_upgrade_kernel():
    """
    Upgrade kernel.
    """
    return sequence([
        run_from_args(['yum', 'upgrade', '-y', 'kernel']),
        Comment(comment="# The upgrade doesn't make the new kernel default."),
        run_from_args(['grubby', '--set-default-index', '0']),
    ])


def task_upgrade_kernel_centos():
    return sequence([
        run_from_args([
            "yum", "install", "-y", "kernel-devel", "kernel"]),
        # For dkms and ... ?
        run_from_args([
            "yum", "install", "-y", "epel-release"]),
        run_from_args(['sync']),
    ])


def task_install_kernel_devel():
    """
    Install development headers corresponding to running kernel.

    This is so we can compile zfs.
    """
    return sequence([run("""
UNAME_R=$(uname -r)
PV=${UNAME_R%.*}
KV=${PV%%-*}
SV=${PV##*-}
ARCH=$(uname -m)
yum install -y https://kojipkgs.fedoraproject.org/packages/kernel/\
${KV}/${SV}/${ARCH}/kernel-devel-${UNAME_R}.rpm
""")])


def task_enable_docker():
    """
    Start docker and configure it to start automatically.
    """
    return sequence([
        run_from_args(["systemctl", "enable", "docker.service"]),
        run_from_args(["systemctl", "start", "docker.service"]),
    ])


def configure_firewalld(rule):
    """
    Configure firewalld with a given rule.

    :param list rule: List of `firewall-cmd` arguments.
    """
    return sequence([
        run_from_args(command + rule)
        for command in [['firewall-cmd', '--permanent'],
                        ['firewall-cmd']]])


def task_disable_firewall():
    """
    Disable the firewall.
    """
    return configure_firewalld(
        ['--direct', '--add-rule', 'ipv4', 'filter',
         'FORWARD', '0', '-j', 'ACCEPT'])


def task_enable_flocker_control():
    """
    Enable flocker-control service.
    """
    return sequence([
        run_from_args(['systemctl', 'enable', 'flocker-control']),
        run_from_args(['systemctl', 'start', 'flocker-control']),
    ])


def task_open_control_firewall():
    """
    Open the firewall for flocker-control.
    """
    return sequence([
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
    return sequence([
        put(
            path='/etc/sysconfig/flocker-agent',
            content=AGENT_CONFIG % {
                'node_name': node_name,
                'control_node': control_node
            },
        ),
        run_from_args(['systemctl', 'enable', 'flocker-agent']),
        run_from_args(['systemctl', 'start', 'flocker-agent']),
    ])


def task_create_flocker_pool_file():
    """
    Create a file-back zfs pool for flocker.
    """
    return sequence([
        run('mkdir -p /var/opt/flocker'),
        run('truncate --size 10G /var/opt/flocker/pool-vdev'),
        run('zpool create flocker /var/opt/flocker/pool-vdev'),
    ])


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
        run(command="yum install -y " + ZFS_REPO[distribution]),
        run(command="yum install -y " + CLUSTERHQ_REPO[distribution])
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
        commands.append(put(content=repo,
                            path='/etc/yum.repos.d/clusterhq-build.repo'))
        branch_opt = ['--enablerepo=clusterhq-build']
    else:
        branch_opt = []

    if package_source.os_version:
        package = 'clusterhq-flocker-node-%s' % (package_source.os_version,)
    else:
        package = 'clusterhq-flocker-node'

    commands.append(run_from_args(
        ["yum", "install"] + branch_opt + ["-y", package]))

    return sequence(commands)


def task_upgrade_selinux():
    return sequence([
        run_from_args(['yum', 'upgrade', '-y', 'selinux-policy']),
    ])


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
    return parallel([
        run_from_args(['docker', 'pull', image]) for image in images
    ])


def task_enable_updates_testing(distribution):
    """
    Enable the distribution's proposed updates repository.

    :param bytes distribution: See func:`task_install_flocker`
    """
    if distribution == 'fedora-20':
        return sequence([
            run_from_args(['yum', 'install', '-y', 'yum-utils']),
            run_from_args([
                'yum-config-manager', '--enable', 'updates-testing'])
        ])
    else:
        raise NotImplementedError


def task_enable_docker_head_repository(distribution):
    """
    Enable the distribution's repository containing in-development docker
    builds.

    :param bytes distribution: See func:`task_install_flocker`
    """
    if distribution == 'fedora-20':
        return sequence([
            run_from_args(['yum', 'install', '-y', 'yum-utils']),
            run_from_args([
                'yum-config-manager',
                '--add-repo',
                'https://copr.fedoraproject.org/coprs/lsm5/docker-io/repo/fedora-20/lsm5-docker-io-fedora-20.repo',  # noqa
            ])
        ])
    elif distribution == "centos-7":
        return sequence([
            Put(content=dedent("""\
                [virt7-testing]
                name=virt7-testing
                baseurl=http://cbs.centos.org/repos/virt7-testing/x86_64/os/
                enabled=1
                gpgcheck=0
                """),
                path="/etc/yum.repos.d/virt7-testing.repo")
        ])
    else:
        raise NotImplementedError


def task_enable_zfs_testing(distribution):
    """
    Enable the zfs-testing repository.

    :param bytes distribution: See func:`task_install_flocker`
    """
    if distribution in ('fedora-20', 'centos-7'):
        return sequence([
            run_from_args(['yum', 'install', '-y', 'yum-utils']),
            run_from_args([
                'yum-config-manager', '--enable', 'zfs-testing'])
        ])
    else:
        raise NotImplementedError


def provision(distribution, package_source, variants):
    """
    Provision the node for running flocker.

    :param bytes address: Address of the node to provision.
    :param bytes username: Username to connect as.
    :param bytes distribution: See func:`task_install_flocker`
    :param PackageSource package_source: See func:`task_install_flocker`
    :param set variants: The set of variant configurations to use when
        provisioning
    """
    commands = []

    if Variants.DISTRO_TESTING in variants:
        commands.append(task_enable_updates_testing(distribution))
    if Variants.DOCKER_HEAD in variants:
        commands.append(task_enable_docker_head_repository(distribution))
    if Variants.ZFS_TESTING in variants:
        commands.append(task_enable_zfs_testing(distribution))

    if distribution in ('fedora-20',):
        commands.append(task_install_kernel_devel())

    commands += [
        task_install_flocker(package_source=package_source,
                             distribution=distribution),
        task_enable_docker(),
        task_create_flocker_pool_file(),
        task_pull_docker_images(),
    ]
    return sequence(commands)


def configure_cluster(control_node, agent_nodes):
    """
    Configure flocker-control and flocker-agent on a collection of nodes.

    :param bytes control_node: The address of the control node.
    :param list agent_nodes: List of addresses of agent nodes.
    """
    run_with_crochet(
        username='root',
        address=control_node,
        commands=task_enable_flocker_control(),
    )
    for node in agent_nodes:
        configure_ssh(node, 22)
        run_with_crochet(
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
    run_with_crochet(
        username='root',
        address=control_node,
        commands=run_from_args(['systemctl', 'stop', 'flocker-control']),
    )
    for node in agent_nodes:
        run_with_crochet(
            username='root',
            address=node,
            commands=run_from_args(['systemctl', 'stop', 'flocker-agent']),
        )
