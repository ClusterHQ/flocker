# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.provision.test.test_install -*-

"""
Install flocker on a remote node.
"""

import posixpath
from textwrap import dedent
from urlparse import urljoin, urlparse
from effect import Func, Effect
import yaml

from zope.interface import implementer

from characteristic import attributes
from pyrsistent import PRecord, field

from ._libcloud import INode
from ._common import PackageSource, Variants
from ._ssh import (
    run, run_from_args,
    sudo, sudo_from_args,
    put,
    run_remotely
)
from ._effect import sequence

from flocker import __version__ as version
from flocker.cli import configure_ssh
from flocker.common.version import (
    get_installable_version, get_package_key_suffix, is_release,
)

# A systemctl sub-command to start or restart a service.  We use restart here
# so that if it is already running it gets restart (possibly necessary to
# respect updated configuration) and because restart will also start it if it
# is not running.
START = "restart"

ZFS_REPO = {
    'centos-7': "https://s3.amazonaws.com/archive.zfsonlinux.org/"
                "epel/zfs-release.el7.noarch.rpm",
}

ARCHIVE_BUCKET = 'clusterhq-archive'


def get_repository_url(distribution, flocker_version):
    """
    Return the URL for the repository of a given distribution.

    For ``yum``-using distributions this gives the URL to a package that adds
    entries to ``/etc/yum.repos.d``. For ``apt``-using distributions, this
    gives the URL for a repo containing a Packages(.gz) file.

    :param bytes distribution: The Linux distribution to get a repository for.
    :param bytes flocker_version: The version of Flocker to get a repository
        for.

    :return bytes: The URL pointing to a repository of packages.
    :raises: ``UnsupportedDistribution`` if the distribution is unsupported.
    """
    distribution_to_url = {
        # TODO instead of hardcoding keys, use the _to_Distribution map
        # and then choose the name
        'centos-7': "https://{archive_bucket}.s3.amazonaws.com/"
                    "{key}/clusterhq-release$(rpm -E %dist).noarch.rpm".format(
                        archive_bucket=ARCHIVE_BUCKET,
                        key='centos',
                        ),

        # This could hardcode the version number instead of using
        # ``lsb_release`` but that allows instructions to be shared between
        # versions, and for earlier error reporting if you try to install on a
        # separate version. The $(ARCH) part must be left unevaluated, hence
        # the backslash escapes (one to make shell ignore the $ as a
        # substitution marker, and then doubled to make Python ignore the \ as
        # an escape marker). The output of this value then goes into
        # /etc/apt/sources.list which does its own substitution on $(ARCH)
        # during a subsequent apt-get update

        'ubuntu-14.04': 'https://{archive_bucket}.s3.amazonaws.com/{key}/'
                        '$(lsb_release --release --short)/\\$(ARCH)'.format(
                            archive_bucket=ARCHIVE_BUCKET,
                            key='ubuntu' + get_package_key_suffix(
                                flocker_version),
                        ),

        'ubuntu-15.04': 'https://{archive_bucket}.s3.amazonaws.com/{key}/'
                        '$(lsb_release --release --short)/\\$(ARCH)'.format(
                            archive_bucket=ARCHIVE_BUCKET,
                            key='ubuntu' + get_package_key_suffix(
                                flocker_version),
                        ),
    }

    try:
        return distribution_to_url[distribution]
    except KeyError:
        raise UnsupportedDistribution()


def get_repo_options(flocker_version):
    """
    Get a list of options for enabling necessary yum repositories.

    :param bytes flocker_version: The version of Flocker to get options for.
    :return: List of bytes for enabling (or not) a testing repository.
    """
    is_dev = not is_release(flocker_version)
    if is_dev:
        return ['--enablerepo=clusterhq-testing']
    else:
        return []


class UnsupportedDistribution(Exception):
    """
    Raised if trying to support a distribution which is not supported.
    """


@attributes(['distribution'])
class DistributionNotSupported(NotImplementedError):
    """
    Raised when the provisioning step is not supported on the given
    distribution.

    :ivar bytes distribution: The distribution that isn't supported.
    """
    def __str__(self):
        return "Distribution not supported: %s" % (self.distribution,)


@implementer(INode)
class ManagedNode(PRecord):
    """
    A node managed by some other system (eg by hand or by another piece of
    orchestration software).
    """
    address = field(type=bytes, mandatory=True)
    private_address = field(type=(bytes, type(None)),
                            initial=None, mandatory=True)
    distribution = field(type=bytes, mandatory=True)


def task_client_installation_test():
    """
    Check that the CLI is working.
    """
    return run_from_args(['flocker-deploy', '--version'])


def install_cli_commands_yum(distribution, package_source):
    """
    Install Flocker CLI on CentOS.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :return: a sequence of commands to run on the distribution
    """
    if package_source.branch:
        # A development branch has been selected - add its Buildbot repo
        use_development_branch = True
        result_path = posixpath.join(
            '/results/omnibus/', package_source.branch, distribution)
        base_url = urljoin(package_source.build_server, result_path)
    else:
        use_development_branch = False

    commands = [
        sudo(command="yum install -y " + get_repository_url(
            distribution=distribution,
            flocker_version=get_installable_version(version))),
    ]

    if use_development_branch:
        repo = dedent(b"""\
            [clusterhq-build]
            name=clusterhq-build
            baseurl=%s
            gpgcheck=0
            enabled=0
            """) % (base_url,)
        commands.append(put(content=repo,
                            path='/tmp/clusterhq-build.repo'))
        commands.append(sudo_from_args([
            'cp', '/tmp/clusterhq-build.repo',
            '/etc/yum.repos.d/clusterhq-build.repo']))
        repo_options = ['--enablerepo=clusterhq-build']
    else:
        repo_options = get_repo_options(
            flocker_version=get_installable_version(version))

    if package_source.os_version:
        package = 'clusterhq-flocker-cli-%s' % (package_source.os_version,)
    else:
        package = 'clusterhq-flocker-cli'

    # Install Flocker CLI and all dependencies

    commands.append(sudo_from_args(
        ["yum", "install"] + repo_options + ["-y", package]))

    return sequence(commands)


def install_cli_commands_ubuntu(distribution, package_source):
    """
    Install flocker CLI on Ubuntu.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :return: a sequence of commands to run on the distribution
    """
    if package_source.branch:
        # A development branch has been selected - add its Buildbot repo
        use_development_branch = True
        result_path = posixpath.join(
            '/results/omnibus/', package_source.branch, distribution)
        base_url = urljoin(package_source.build_server, result_path)
    else:
        use_development_branch = False

    commands = [
        # Minimal images often have cleared apt caches and are missing
        # packages that are common in a typical release.  These commands
        # ensure that we start from a good base system with the required
        # capabilities, particularly that the add-apt-repository command
        # and HTTPS URLs are supported.
        # FLOC-1880 will ensure these are necessary and sufficient.
        sudo_from_args(["apt-get", "update"]),
        sudo_from_args([
            "apt-get", "-y", "install", "apt-transport-https",
            "software-properties-common"]),

        # Add ClusterHQ repo for installation of Flocker packages.
        sudo(command='add-apt-repository -y "deb {} /"'.format(
            get_repository_url(
                distribution=distribution,
                flocker_version=get_installable_version(version))))
        ]

    if use_development_branch:
        # Add BuildBot repo for running tests
        commands.append(sudo_from_args([
            "add-apt-repository", "-y", "deb {} /".format(base_url)]))
        # During a release, the ClusterHQ repo may contain packages with
        # a higher version number than the Buildbot repo for a branch.
        # Use a pin file to ensure that any Buildbot repo has higher
        # priority than the ClusterHQ repo.
        buildbot_host = urlparse(package_source.build_server).hostname
        commands.append(put(dedent('''\
            Package:  *
            Pin: origin {}
            Pin-Priority: 900
            '''.format(buildbot_host)), '/tmp/apt-pref'))
        commands.append(sudo_from_args([
            'mv', '/tmp/apt-pref', '/etc/apt/preferences.d/buildbot-900']))

    # Update to read package info from new repos
    commands.append(sudo_from_args(["apt-get", "update"]))

    if package_source.os_version:
        package = 'clusterhq-flocker-cli=%s' % (package_source.os_version,)
    else:
        package = 'clusterhq-flocker-cli'

    # Install Flocker CLI and all dependencies
    commands.append(sudo_from_args([
        'apt-get', '-y', '--force-yes', 'install', package]))

    return sequence(commands)


_task_install_commands = {
    'centos-7': install_cli_commands_yum,
    'ubuntu-14.04': install_cli_commands_ubuntu,
    'ubuntu-15.04': install_cli_commands_ubuntu,
}


def task_install_cli(distribution, package_source=PackageSource()):
    """
    Install flocker CLI on a distribution.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :return: a sequence of commands to run on the distribution
    """
    return _task_install_commands[distribution](distribution, package_source)


def install_cli(package_source, node):
    """
    Return an effect to run the CLI installation tasks on a remote node.

    :param package_source: Package source description
    :param node: Remote node description
    """
    return run_remotely(
        node.get_default_username(), node.address,
        task_install_cli(node.distribution, package_source))


def task_configure_brew_path():
    """
    Configure non-interactive shell to use all paths.

    By default, OSX provides a minimal $PATH, for programs run via SSH. In
    particular /usr/local/bin (which contains `brew`) isn't in the path. This
    configures the path to have it there.
    """
    return put(
        path='.bashrc',
        content=dedent("""\
            if [ -x /usr/libexec/path_helper ]; then
                eval `/usr/libexec/path_helper -s`
            fi
            """))


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
    if distribution == 'centos-7':
        return sequence([
            run_from_args([
                "yum", "install", "-y", "kernel-devel", "kernel"]),
            run_from_args(['sync']),
        ])
    elif distribution == 'ubuntu-14.04':
        # Not required.
        return sequence([])
    else:
        raise DistributionNotSupported(distribution=distribution)


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
    elif distribution in ('ubuntu-14.04',):
        # Ubuntu does not have SELinux enabled
        return sequence([])
    else:
        raise DistributionNotSupported(distribution=distribution)


def _remove_private_key(content):
    """
    Remove most of the contents of a private key file for logging.
    """
    prefix = '-----BEGIN PRIVATE KEY-----'
    suffix = '-----END PRIVATE KEY-----'
    start = content.find(prefix)
    if start < 0:
        # no private key
        return content
    # Keep prefix, subsequent newline, and 4 characters at start of key
    trim_start = start + len(prefix) + 5
    end = content.find(suffix, trim_start)
    if end < 0:
        end = len(content)
    # Keep suffix and previous 4 characters and newline at end of key
    trim_end = end - 5
    if trim_end <= trim_start:
        # strangely short key, keep all content
        return content
    return content[:trim_start] + '...REMOVED...' + content[trim_end:]


def task_install_control_certificates(ca_cert, control_cert, control_key):
    """
    Install certificates and private key required by the control service.

    :param FilePath ca_cert: Path to CA certificate on local machine.
    :param FilePath control_cert: Path to control service certificate on
        local machine.
    :param FilePath control_key: Path to control service private key
        local machine.
    """
    # Be better if permissions were correct from the start.
    # https://clusterhq.atlassian.net/browse/FLOC-1922
    return sequence([
        run('mkdir -p /etc/flocker'),
        run('chmod u=rwX,g=,o= /etc/flocker'),
        put(path="/etc/flocker/cluster.crt", content=ca_cert.getContent()),
        put(path="/etc/flocker/control-service.crt",
            content=control_cert.getContent()),
        put(path="/etc/flocker/control-service.key",
            content=control_key.getContent(),
            log_content_filter=_remove_private_key),
        ])


def task_install_node_certificates(ca_cert, node_cert, node_key):
    """
    Install certificates and private key required by a node.

    :param FilePath ca_cert: Path to CA certificate on local machine.
    :param FilePath node_cert: Path to node certificate on
        local machine.
    :param FilePath node_key: Path to node private key
        local machine.
    """
    # Be better if permissions were correct from the start.
    # https://clusterhq.atlassian.net/browse/FLOC-1922
    return sequence([
        run('mkdir -p /etc/flocker'),
        run('chmod u=rwX,g=,o= /etc/flocker'),
        put(path="/etc/flocker/cluster.crt", content=ca_cert.getContent()),
        put(path="/etc/flocker/node.crt",
            content=node_cert.getContent()),
        put(path="/etc/flocker/node.key",
            content=node_key.getContent(),
            log_content_filter=_remove_private_key),
        ])


def task_enable_docker(distribution):
    """
    Start docker and configure it to start automatically.
    """
    if distribution in ('centos-7',):
        return sequence([
            run_from_args(["systemctl", "enable", "docker.service"]),
            run_from_args(["systemctl", "start", "docker.service"]),
        ])
    elif distribution == 'ubuntu-14.04':
        # Ubuntu enables docker service during installation
        return sequence([])
    else:
        raise DistributionNotSupported(distribution=distribution)


def open_firewalld(service):
    """
    Open firewalld port for a service.

    :param str service: Name of service.
    """
    return sequence([
        run_from_args(command + [service])
        for command in [['firewall-cmd', '--permanent', '--add-service'],
                        ['firewall-cmd', '--add-service']]])


def open_ufw(service):
    """
    Open ufw port for a service.

    :param str service: Name of service.
    """
    return sequence([
        run_from_args(['ufw', 'allow', service])
        ])


def task_enable_flocker_control(distribution):
    """
    Enable flocker-control service.
    """
    if distribution in ('centos-7',):
        return sequence([
            run_from_args(['systemctl', 'enable', 'flocker-control']),
            run_from_args(['systemctl', START, 'flocker-control']),
        ])
    elif distribution == 'ubuntu-14.04':
        # Since the flocker-control service is currently installed
        # alongside the flocker-dataset-agent service, the default control
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
            run("echo 'flocker-control-api\t4523/tcp\t\t\t# Flocker Control API port' >> /etc/services"),  # noqa
            run("echo 'flocker-control-agent\t4524/tcp\t\t\t# Flocker Control Agent port' >> /etc/services"),  # noqa
            run_from_args(['service', 'flocker-control', 'start']),
        ])
    else:
        raise DistributionNotSupported(distribution=distribution)


def task_open_control_firewall(distribution):
    """
    Open the firewall for flocker-control.
    """
    if distribution in ('centos-7',):
        open_firewall = open_firewalld
    elif distribution == 'ubuntu-14.04':
        open_firewall = open_ufw
    else:
        raise DistributionNotSupported(distribution=distribution)

    return sequence([
        open_firewall(service)
        for service in ['flocker-control-api', 'flocker-control-agent']
    ])


# Set of dataset fields which are *not* sensitive.  Only fields in this
# set are logged.  This should contain everything except usernames and
# passwords (or equivalents).  Implemented as a whitelist in case new
# security fields are added.
_ok_to_log = frozenset((
    'auth_plugin',
    'auth_url',
    'backend',
    'region',
    'zone',
    ))


def _remove_dataset_fields(content):
    """
    Remove non-whitelisted fields from dataset for logging.
    """
    content = yaml.safe_load(content)
    dataset = content['dataset']
    for key in dataset:
        if key not in _ok_to_log:
            dataset[key] = 'REMOVED'
    return yaml.safe_dump(content)


def task_configure_flocker_agent(control_node, dataset_backend,
                                 dataset_backend_configuration):
    """
    Configure the flocker agents by writing out the configuration file.

    :param bytes control_node: The address of the control agent.
    :param DatasetBackend dataset_backend: The volume backend the nodes are
        configured with.
    :param dict dataset_backend_configuration: The backend specific
        configuration options.
    """
    dataset_backend_configuration = dataset_backend_configuration.copy()
    dataset_backend_configuration.update({
        u"backend": dataset_backend.name,
    })

    put_config_file = put(
        path='/etc/flocker/agent.yml',
        content=yaml.safe_dump(
            {
                "version": 1,
                "control-service": {
                    "hostname": control_node,
                    "port": 4524,
                },
                "dataset": dataset_backend_configuration,
            },
        ),
        log_content_filter=_remove_dataset_fields
    )
    return sequence([put_config_file])


def task_enable_flocker_agent(distribution):
    """
    Enable the flocker agents.

    :param bytes distribution: The distribution name.
    """
    if distribution in ('centos-7',):
        return sequence([
            run_from_args(['systemctl', 'enable', 'flocker-dataset-agent']),
            run_from_args(['systemctl', START, 'flocker-dataset-agent']),
            run_from_args(['systemctl', 'enable', 'flocker-container-agent']),
            run_from_args(['systemctl', START, 'flocker-container-agent']),
        ])
    elif distribution == 'ubuntu-14.04':
        return sequence([
            run_from_args(['service', 'flocker-dataset-agent', 'start']),
            run_from_args(['service', 'flocker-container-agent', 'start']),
        ])
    else:
        raise DistributionNotSupported(distribution=distribution)


def task_create_flocker_pool_file():
    """
    Create a file-back zfs pool for flocker.
    """
    return sequence([
        run('mkdir -p /var/opt/flocker'),
        run('truncate --size 10G /var/opt/flocker/pool-vdev'),
        run('zpool create flocker /var/opt/flocker/pool-vdev'),
    ])


def task_install_zfs(distribution, variants=set()):
    """
    Install ZFS on a node.

    :param bytes distribution: The distribution the node is running.
    :param set variants: The set of variant configurations to use when
    """
    commands = []
    if distribution == 'ubuntu-14.04':
        commands += [
            # ZFS not available in base Ubuntu - add ZFS repo
            run_from_args([
                "add-apt-repository", "-y", "ppa:zfs-native/stable"]),
        ]
        commands += [
            # Update to read package info from new repos
            run_from_args([
                "apt-get", "update"]),
            # Package spl-dkms sometimes does not have libc6-dev as a
            # dependency, add it before ZFS installation requires it.
            # See https://github.com/zfsonlinux/zfs/issues/3298
            run_from_args(["apt-get", "-y", "install", "libc6-dev"]),
            run_from_args(['apt-get', '-y', 'install', 'zfsutils']),
            ]

    elif distribution in ('centos-7',):
        commands += [
            run_from_args(["yum", "install", "-y", ZFS_REPO[distribution]]),
        ]
        if distribution == 'centos-7':
            commands.append(
                run_from_args(["yum", "install", "-y", "epel-release"]))

        if Variants.ZFS_TESTING in variants:
            commands += [
                run_from_args(['yum', 'install', '-y', 'yum-utils']),
                run_from_args([
                    'yum-config-manager', '--enable', 'zfs-testing'])
            ]
        commands += [
            run_from_args(['yum', 'install', '-y', 'zfs']),
        ]
    else:
        raise DistributionNotSupported(distribution)

    return sequence(commands)


def configure_zfs(node, variants):
    """
    Configure ZFS for use as a Flocker backend.

    :param INode node: The node to configure ZFS on.
    :param set variants: The set of variant configurations to use when

    :return Effect:
    """
    return sequence([
        run_remotely(
            username='root',
            address=node.address,
            commands=task_upgrade_kernel(
                distribution=node.distribution),
        ),
        node.reboot(),
        run_remotely(
            username='root',
            address=node.address,
            commands=sequence([
                task_install_zfs(
                    distribution=node.distribution,
                    variants=variants),
                task_create_flocker_pool_file(),
            ]),
        ),
        Effect(
            Func(lambda: configure_ssh(node.address, 22))),
    ])


def _uninstall_flocker_ubuntu1404():
    """
    Return an ``Effect`` for uninstalling the Flocker package from an Ubuntu
    14.04 machine.
    """
    return run_from_args([
        b"apt-get", b"remove", b"-y", b"--purge", b"clusterhq-python-flocker",
    ])


def _uninstall_flocker_centos7():
    """
    Return an ``Effect`` for uninstalling the Flocker package from a CentOS 7
    machine.
    """
    return sequence([
        run_from_args([
            b"yum", b"erase", b"-y", b"clusterhq-python-flocker",
        ]),
        run_from_args([
            b"yum", b"erase", b"-y", b"clusterhq-release",
        ]),
    ])


_flocker_uninstallers = {
    "ubuntu-14.04": _uninstall_flocker_ubuntu1404,
    "centos-7": _uninstall_flocker_centos7,
}


def task_uninstall_flocker(distribution):
    """
    Return an ``Effect`` for uninstalling the Flocker package from the given
    distribution.
    """
    return _flocker_uninstallers[distribution]()


def uninstall_flocker(nodes):
    """
    Return an ``Effect`` for uninstalling the Flocker package from all of the
    given nodes.
    """
    return _run_on_all_nodes(
        nodes,
        task=lambda node: task_uninstall_flocker(node.distribution)
    )


def task_install_flocker(
    distribution=None,
    package_source=PackageSource(),
):
    """
    Install flocker cluster on a distribution.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :raises: ``UnsupportedDistribution`` if the distribution is unsupported.
    """
    if package_source.branch:
        # A development branch has been selected - add its Buildbot repo
        use_development_branch = True
        result_path = posixpath.join(
            '/results/omnibus/', package_source.branch, distribution)
        base_url = urljoin(package_source.build_server, result_path)
    else:
        use_development_branch = False

    if distribution in ('ubuntu-14.04', 'ubuntu-15.04'):
        commands = [
            # Ensure add-apt-repository command and HTTPS URLs are supported
            # FLOC-1880 will ensure these are necessary and sufficient
            run_from_args([
                "apt-get", "-y", "install", "apt-transport-https",
                "software-properties-common"]),
            # Add Docker repo for recent Docker versions
            run_from_args([
                "add-apt-repository", "-y", "ppa:james-page/docker"]),
            # Add ClusterHQ repo for installation of Flocker packages.
            run(command='add-apt-repository -y "deb {} /"'.format(
                get_repository_url(
                    distribution=distribution,
                    flocker_version=get_installable_version(version)))),
        ]

        if use_development_branch:
            # Add BuildBot repo for testing
            commands.append(run_from_args([
                "add-apt-repository", "-y", "deb {} /".format(base_url)]))
            # During a release, the ClusterHQ repo may contain packages with
            # a higher version number than the Buildbot repo for a branch.
            # Use a pin file to ensure that any Buildbot repo has higher
            # priority than the ClusterHQ repo.
            buildbot_host = urlparse(package_source.build_server).hostname
            commands.append(put(
                dedent('''\
                    Package:  *
                    Pin: origin {}
                    Pin-Priority: 900
                    '''.format(buildbot_host)),
                '/etc/apt/preferences.d/buildbot-900'))

        commands += [
            # Update to read package info from new repos
            run_from_args([
                "apt-get", "update"]),
            ]

        if package_source.os_version:
            package = 'clusterhq-flocker-node=%s' % (
                package_source.os_version,)
        else:
            package = 'clusterhq-flocker-node'

        # Install Flocker node and all dependencies
        commands.append(run_from_args([
            'apt-get', '-y', '--force-yes', 'install', package]))

        return sequence(commands)
    elif distribution in ('centos-7',):
        commands = [
            run(command="yum clean all"),
            run(command="yum install -y " + get_repository_url(
                distribution=distribution,
                flocker_version=get_installable_version(version)))
        ]

        if use_development_branch:
            repo = dedent(b"""\
                [clusterhq-build]
                name=clusterhq-build
                baseurl=%s
                gpgcheck=0
                enabled=0
                """) % (base_url,)
            commands.append(put(content=repo,
                                path='/etc/yum.repos.d/clusterhq-build.repo'))
            repo_options = ['--enablerepo=clusterhq-build']
        else:
            repo_options = get_repo_options(
                flocker_version=get_installable_version(version))

        if package_source.os_version:
            package = 'clusterhq-flocker-node-%s' % (
                package_source.os_version,)
        else:
            package = 'clusterhq-flocker-node'

        commands.append(run_from_args(
            ["yum", "install"] + repo_options + ["-y", package]))

        return sequence(commands)
    else:
        raise UnsupportedDistribution()


ACCEPTANCE_IMAGES = [
    "postgres:latest",
    "clusterhq/mongodb:latest",
    "python:2.7-slim",
    "busybox",
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
    raise DistributionNotSupported(distribution=distribution)


def task_enable_docker_head_repository(distribution):
    """
    Enable the distribution's repository containing in-development docker
    builds.

    :param bytes distribution: See func:`task_install_flocker`
    """
    if distribution == "centos-7":
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
        raise DistributionNotSupported(distribution=distribution)


def provision(distribution, package_source, variants):
    """
    Provision the node for running flocker.

    This drives all the common node installation steps in:
     * http://doc-dev.clusterhq.com/gettingstarted/installation.html

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

    commands.append(
        task_install_flocker(
            package_source=package_source, distribution=distribution))
    if distribution in ('centos-7'):
        commands.append(task_disable_selinux(distribution))
    commands.append(task_enable_docker(distribution))
    return sequence(commands)


def _run_on_all_nodes(nodes, task):
    """
    Run some commands on some nodes.

    :param nodes: An iterable of ``Node`` instances where the commands should
        be run.
    :param task: A one-argument callable which is called with each ``Node`` and
        should return the ``Effect`` to run on that node.

    :return: An ``Effect`` that runs the commands on a group of nodes.
    """
    return sequence(list(
        run_remotely(
            username='root',
            address=node.address,
            commands=task(node),
        )
        for node in nodes
    ))


def install_flocker(nodes, package_source):
    """
    Return an ``Effect`` that installs a certain version of Flocker on the
    given nodes.

    :param nodes: An iterable of ``Node`` instances on which to install
        Flocker.
    :param PackageSource package_source: The version of Flocker to install.

    :return: An ``Effect`` which installs Flocker on the nodes.
    """
    return _run_on_all_nodes(
        nodes,
        task=lambda node: task_install_flocker(
            distribution=node.distribution,
            package_source=package_source,
        )
    )


def configure_cluster(cluster, dataset_backend_configuration):
    """
    Configure flocker-control, flocker-dataset-agent and
    flocker-container-agent on a collection of nodes.

    :param Cluster cluster: Description of the cluster to configure.

    :param dict dataset_backend_configuration: Configuration parameters to
        supply to the dataset backend.
    """
    return sequence([
        run_remotely(
            username='root',
            address=cluster.control_node.address,
            commands=sequence([
                task_install_control_certificates(
                    cluster.certificates.cluster.certificate,
                    cluster.certificates.control.certificate,
                    cluster.certificates.control.key),
                task_enable_flocker_control(cluster.control_node.distribution),
                ]),
        ),
        sequence([
            sequence([
                run_remotely(
                    username='root',
                    address=node.address,
                    commands=sequence([
                        task_install_node_certificates(
                            cluster.certificates.cluster.certificate,
                            certnkey.certificate,
                            certnkey.key),
                        task_configure_flocker_agent(
                            control_node=cluster.control_node.address,
                            dataset_backend=cluster.dataset_backend,
                            dataset_backend_configuration=(
                                dataset_backend_configuration
                            ),
                        ),
                        task_enable_flocker_agent(
                            distribution=node.distribution,
                        )]),
                    ),
            ]) for certnkey, node
            in zip(cluster.certificates.nodes, cluster.agent_nodes)
        ])
    ])
