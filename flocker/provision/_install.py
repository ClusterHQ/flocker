# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.provision.test.test_install -*-

"""
Install flocker on a remote node.
"""

import posixpath
from textwrap import dedent
from urlparse import urljoin
from effect import Func, Effect

from ._common import PackageSource, Variants, Kernel
from ._ssh import (
    run, run_from_args,
    sudo_from_args,
    put, comment,
    run_remotely
)
from ._effect import sequence

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


def task_test_homebrew(recipe):
    """
    The commands used to install a Homebrew recipe for Flocker and test it.

    This taps the ClusterHQ/tap tap, which means that Homebrew looks in the
    ClusterHQ/homebrew-tap GitHub repository for any recipe name given.

    :param bytes recipe: The name of a recipe in a either the official Homebrew
        tap or ClusterHQ/tap, or a URL pointing to a recipe.
    :return Effect: Commands used to install a Homebrew recipe for Flocker and
        test it.
    """
    return sequence([
        run_from_args(['brew', 'tap', 'ClusterHQ/tap']),
        run("brew update"),
        run("brew install {recipe}".format(recipe=recipe)),
        run("brew test {recipe}".format(recipe=recipe)),
    ])


def task_install_ssh_key():
    """
    Install the authorized ssh keys of the current user for root as well.
    """
    return sequence([
        sudo_from_args(['cp', '.ssh/authorized_keys',
                        '/root/.ssh/authorized_keys']),
    ])


def task_upgrade_kernel(distribution):
    """
    Upgrade kernel.
    """
    if distribution == 'fedora-20':
        return sequence([
            run_from_args(['yum', 'upgrade', '-y', 'kernel']),
            comment(
                comment="The upgrade doesn't make the new kernel default."),
            run_from_args(['grubby', '--set-default-index', '0']),
        ])
    elif distribution == 'centos-7':
        return sequence([
            run_from_args([
                "yum", "install", "-y", "kernel-devel", "kernel"]),
            run_from_args(['sync']),
        ])
    else:
        raise NotImplementedError()


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


DIGITALOCEAN_KERNEL = Kernel(
    version="3.17.8",
    release="200",
    distribution="fc20",
    architecture="x86_64"
)


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
    return sequence([
        run_from_args(['yum', 'update', '-y', url]),
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


def task_disable_selinux(distribution):
    """
    Disable SELinux for this session and permanently.
    XXX: Remove this when we work out suitable SELinux settings.
    See https://clusterhq.atlassian.net/browse/FLOC-619.
    """
    if distribution in ('centos-7',):
        return sequence([
            run("if selinuxenabled; then setenforce 0; fi"),
            run("test -e /etc/selinux/config && "
                "sed --in-place='.preflocker' "
                "'s/^SELINUX=.*$/SELINUX=disabled/g' "
                "/etc/selinux/config"),
        ])
    else:
        raise NotImplementedError()


def task_enable_docker(distribution):
    """
    Start docker and configure it to start automatically.
    """
    if distribution in ('fedora-20', 'centos-7'):
        return sequence([
            run_from_args(["systemctl", "enable", "docker.service"]),
            run_from_args(["systemctl", "start", "docker.service"]),
        ])
    else:
        # Ubuntu enables docker service during installation
        return sequence([])


def configure_firewalld(rule):
    """
    Configure firewalld with a given rule.

    :param list rule: List of `firewall-cmd` arguments.
    """
    return sequence([
        run_from_args(command + rule)
        for command in [['firewall-cmd', '--permanent'],
                        ['firewall-cmd']]])


def task_enable_flocker_control(distribution):
    """
    Enable flocker-control service.
    """
    if distribution in ('centos-7', 'fedora-20'):
        return sequence([
            run_from_args(['systemctl', 'enable', 'flocker-control']),
            run_from_args(['systemctl', 'start', 'flocker-control']),
        ])
    elif distribution == 'ubuntu-14.04':
        # Since the flocker-control service is currently installed
        # alongside the flocker-agent service, the default control
        # service configuration does not automatically start the
        # service.  Here, we provide an override file to start it.
        return sequence([
            put(
                path='/etc/init/flocker-control.override',
                content=dedent('''\
                    start on runlevel [2345]
                    stop on runlevel [016]
                    '''),
            ),
            run_from_args(['service', 'flocker-control', 'start']),
        ])
    else:
        raise NotImplementedError()


def task_open_control_firewall():
    """
    Open the firewall for flocker-control.
    """
    return sequence([
        configure_firewalld(['--add-service', service])
        for service in ['flocker-control-api', 'flocker-control-agent']
    ])


AGENT_CONFIG = """\
FLOCKER_NODE_NAME=%(node_name)s
FLOCKER_CONTROL_NODE=%(control_node)s
"""


def task_enable_flocker_agent(distribution, agent_node, control_node):
    """
    Configure and enable flocker-agent.

    :param INode agent_node: The flocker-agent node.
    :param bytes control_node: The address of the control agent.
    """
    if distribution in ('centos-7', 'fedora-20'):
        return sequence([
            put(
                path='/etc/sysconfig/flocker-agent',
                content=AGENT_CONFIG % {
                    'node_name': agent_node,
                    'control_node': control_node
                },
            ),
            run_from_args(['systemctl', 'enable', 'flocker-agent']),
            run_from_args(['systemctl', 'start', 'flocker-agent']),
        ])
    elif distribution == 'ubuntu-14.04':
        return sequence([
            put(
                path='/etc/default/flocker-agent.conf',
                content=AGENT_CONFIG % {
                    'node_name': agent_node,
                    'control_node': control_node
                },
            ),
            run_from_args(['service', 'flocker-agent', 'start']),
        ])
    else:
        raise NotImplementedError()


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
    Install flocker on a distribution.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.
    """
    if package_source.branch:
        result_path = posixpath.join(
            '/results/omnibus/', package_source.branch, distribution)
        base_url = urljoin(package_source.build_server, result_path)
    else:
        base_url = None
    if distribution == 'ubuntu-14.04':
        commands = [
            # Ensure add-apt-repository command is available
            run_from_args([
                "apt-get", "-y", "install", "software-properties-common"]),
            # ZFS not available in base Ubuntu - add ZFS repo
            run_from_args([
                "add-apt-repository", "-y", "ppa:zfs-native/stable"]),
            # Add Docker repo for recent Docker versions
            run_from_args([
                "add-apt-repository", "-y", "ppa:james-page/docker"]),
            ]

        # Add ClusterHQ repo for installation of Flocker packages.
        if base_url:
            commands.append(run_from_args([
                "add-apt-repository", "-y", "deb {} /".format(base_url)]))

        commands += [
            # Update to read package info from new repos
            run_from_args([
                "apt-get", "update"]),
            # Package spl-dkms sometimes does not have libc6-dev as a
            # dependency, add it before ZFS installation requires it.
            run_from_args(["apt-get", "-y", "install", "libc6-dev"]),
            # Install Flocker node and all dependencies
            run_from_args([
                'apt-get', '-y', '--force-yes', 'install',
                'clusterhq-flocker-node']),
            ]
        return sequence(commands)
    else:
        commands = [
            run(command="yum install -y " + ZFS_REPO[distribution]),
            run(command="yum install -y " + CLUSTERHQ_REPO[distribution])
        ]

        if distribution == 'centos-7':
            commands.append(
                run_from_args(["yum", "install", "-y", "epel-release"]))

        if base_url:
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
            package = 'clusterhq-flocker-node-%s' % (
                package_source.os_version,)
        else:
            package = 'clusterhq-flocker-node'

        commands.append(run_from_args(
            ["yum", "install"] + branch_opt + ["-y", package]))

        return sequence(commands)


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
    return sequence([
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
        raise NotImplementedError()


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
            put(content=dedent("""\
                [virt7-testing]
                name=virt7-testing
                baseurl=http://cbs.centos.org/repos/virt7-testing/x86_64/os/
                enabled=1
                gpgcheck=0
                """),
                path="/etc/yum.repos.d/virt7-testing.repo")
        ])
    else:
        raise NotImplementedError()


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
        raise NotImplementedError()


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
        commands.append(task_enable_updates_testing(distribution))
    if Variants.DOCKER_HEAD in variants:
        commands.append(task_enable_docker_head_repository(distribution))
    if Variants.ZFS_TESTING in variants:
        commands.append(task_enable_zfs_testing(distribution))

    if distribution in ('fedora-20',):
        commands.append(task_install_kernel_devel())

    commands.append(
        task_install_flocker(
            package_source=package_source, distribution=distribution))
    if distribution in ('centos-7'):
        commands.append(task_disable_selinux(distribution))
    commands.append(task_enable_docker(distribution))
    commands.append(task_create_flocker_pool_file())
    commands.append(task_pull_docker_images())
    return sequence(commands)


def configure_cluster(control_node, agent_nodes):
    """
    Configure flocker-control and flocker-agent on a collection of nodes.

    :param INode control_node: The control node.
    :param INode agent_nodes: List of agent nodes.
    """
    return sequence([
        run_remotely(
            username='root',
            address=control_node.address,
            commands=task_enable_flocker_control(control_node.distribution),
        ),
        sequence([
            sequence([
                Effect(
                    Func(lambda node=node: configure_ssh(node.address, 22))),
                run_remotely(
                    username='root',
                    address=node.address,
                    commands=task_enable_flocker_agent(
                        distribution=node.distribution,
                        agent_node=node.address,
                        control_node=control_node.address,
                    ),
                ),
            ]) for node in agent_nodes
        ])
    ])
