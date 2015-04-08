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


def task_upgrade_kernel():
    """
    Upgrade kernel.
    """
    return sequence([
        run_from_args(['yum', 'upgrade', '-y', 'kernel']),
        comment(comment="The upgrade doesn't make the new kernel default."),
        run_from_args(['grubby', '--set-default-index', '0']),
    ])


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


def task_upgrade_kernel_centos():
    return sequence([
        run_from_args([
            "yum", "install", "-y", "kernel-devel", "kernel"]),
        run_from_args(['sync']),
    ])


def task_upgrade_kernel_ubuntu():
    # When 15.04 is available then the kernel can be backported from that,
    # similar to `apt-get install linux-image-generic-lts-utopic`.
    packages_url = "http://kernel.ubuntu.com/~kernel-ppa/mainline/v3.18-vivid/"
    packages = [
        "linux-headers-3.18.0-031800-generic_3.18.0-031800.201412071935_amd64.deb",  # noqa
        "linux-headers-3.18.0-031800_3.18.0-031800.201412071935_all.deb",  # noqa
        "linux-image-3.18.0-031800-generic_3.18.0-031800.201412071935_amd64.deb",  # noqa
    ]

    package_install_commands = [
        run_from_args(["wget", packages_url + package]) for package in packages
    ]

    return sequence([
        run_from_args([
            "mkdir", "-p", "/tmp/kernel-packages"]),
        run_from_args([
            "cd", "/tmp/kernel-packages"]),
    ] + package_install_commands + [
        # XXX This brings up a prompt about upgrading grub,
        # somehow work around that, see
        # http://askubuntu.com/questions/187337/unattended-grub-configuration-after-kernel-upgrade  # noqa
        run(command='dpkg -i linux-*.deb'),
        run_from_args(['rm', '-r', '/tmp/kernel-packages']),
    ])


def task_install_requirements_ubuntu():
    return sequence([
        # Add ZFS repo for recent ZFS versions - XXX no minimum version
        # documented
        run_from_args([
            "add-apt-repository", "-y", "ppa:zfs-native/stable"]),
        # Add Docker repo for recent Docker versions - XXX no minimum
        # version documented
        run_from_args([
            "add-apt-repository", "-y", "ppa:james-page/docker"]),
        # Add ClusterHQ repo for installation of Flocker packages.
        run_from_args([
            "add-apt-repository", "-y",
            "deb http://build.clusterhq.com/results/omnibus/master/ubuntu-14.04 /"]),  # noqa
        # Update to read package info from new repos
        run_from_args([
            "apt-get", "update"]),
        # Not clear that an upgrade is required at this point, so leave it out.
        # XXX This brings up a prompt about upgrading grub,
        # somehow work around that, see
        # http://askubuntu.com/questions/187337/unattended-grub-configuration-after-kernel-upgrade
        # run_from_args([
            # "apt-get", "-y", "upgrade"]),
        # Package spl-dkms must be installed as a separate step before
        # installing zfs-dkms
        run_from_args([
            "apt-get", "-y", "install", "spl-dkms"]),
        run_from_args([
            "apt-get", "-y", "install", "zfs-dkms", "zfsutils", "docker.io"]),
    ])


def task_install_flocker_ubuntu():
    return sequence([run_from_args([
        'apt-get', '-y', '--force-yes', 'install', 'clusterhq-python-flocker',
        'clusterhq-flocker-node'])])


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


def task_install_flocker_yum(
        distribution=None,
        package_source=PackageSource()):
    """
    Install flocker on a distribution which uses yum.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.
    """
    commands = [
        run(command="yum install -y " + ZFS_REPO[distribution]),
        run(command="yum install -y " + CLUSTERHQ_REPO[distribution])
    ]

    if distribution == 'centos-7':
        commands.append(
            run_from_args(["yum", "install", "-y", "epel-release"]))

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
    return sequence([
        run_from_args(['docker', 'pull', image]) for image in images
    ])


def task_enable_updates_testing(distribution):
    """
    Enable the distribution's proposed updates repository.

    :param bytes distribution: See func:`task_install_flocker_yum`
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

    :param bytes distribution: See func:`task_install_flocker_yum`
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
        raise NotImplementedError


def task_enable_zfs_testing(distribution):
    """
    Enable the zfs-testing repository.

    :param bytes distribution: See func:`task_install_flocker_yum`
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

    This drives all the common Fedora20 installation steps in:
     * http://doc-dev.clusterhq.com/gettingstarted/installation.html#installing-on-fedora-20 # noqa

    :param bytes address: Address of the node to provision.
    :param bytes username: Username to connect as.
    :param bytes distribution: See func:`task_install_flocker_yum`
    :param PackageSource package_source: See func:`task_install_flocker_yum`
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
        task_install_flocker_yum(
            package_source=package_source, distribution=distribution),
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
    return sequence([
        run_remotely(
            username='root',
            address=control_node,
            commands=task_enable_flocker_control(),
        ),
        sequence([
            sequence([
                Effect(Func(lambda node=node: configure_ssh(node, 22))),
                run_remotely(
                    username='root',
                    address=node,
                    commands=task_enable_flocker_agent(
                        node_name=node,
                        control_node=control_node,
                    ),
                ),
            ]) for node in agent_nodes
        ])
    ])


def stop_cluster(control_node, agent_nodes):
    """
    Stop flocker-control and flocker-agent on a collection of nodes.

    :param bytes control_node: The address of the control node.
    :param list agent_nodes: List of addresses of agent nodes.
    """
    return sequence([
        run_remotely(
            username='root',
            address=control_node,
            commands=run_from_args(['systemctl', 'stop', 'flocker-control']),
        ),
        sequence([
            run_remotely(
                username='root',
                address=node,
                commands=run_from_args(['systemctl', 'stop', 'flocker-agent']),
            )
            for node in agent_nodes
        ])
    ])
