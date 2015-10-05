# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.provision.test.test_install -*-

"""
Install flocker on a remote node.
"""

import posixpath
from textwrap import dedent
from urlparse import urljoin, urlparse
from effect import Func, Effect, parallel
import yaml

from zope.interface import implementer

from characteristic import attributes
from pyrsistent import PRecord, field

from ._libcloud import INode
from ._common import PackageSource, Variants
from ._ssh import (
    run, run_from_args, Run,
    sudo_from_args, Sudo,
    put,
    run_remotely,
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


def is_centos(distribution):
    """
    Determine whether the named distribution is a version of CentOS.

    :param bytes distribution: The name of the distribution to inspect.

    :return: ``True`` if the distribution named is a version of CentOS,
        ``False`` otherwise.
    """
    return distribution.startswith("centos-")


def is_ubuntu(distribution):
    """
    Determine whether the named distribution is a version of Ubuntu.

    :param bytes distribution: The name of the distribution to inspect.

    :return: ``True`` if the distribution named is a version of Ubuntu,
        ``False`` otherwise.
    """
    return distribution.startswith("ubuntu-")


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


def ensure_minimal_setup(package_manager):
    """
    Get any system into a reasonable state for installation.

    Although we could publish these commands in the docs, they add a lot
    of noise for many users.  Ensure that systems have sudo enabled.

    :param bytes package_manager: The package manager (apt, dnf, yum).
    :return: a sequence of commands to run on the distribution
    """
    if package_manager in ('dnf', 'yum'):
        # Fedora/CentOS sometimes configured to require tty for sudo
        # ("sorry, you must have a tty to run sudo"). Disable that to
        # allow automated tests to run.
        return sequence([
            run_from_args([
                'su', 'root', '-c', [package_manager, '-y', 'install', 'sudo']
            ]),
            run_from_args([
                'su', 'root', '-c', [
                    'sed', '--in-place', '-e',
                    's/Defaults.*requiretty/Defaults !requiretty/',
                    '/etc/sudoers'
                ]]),
        ])
    elif package_manager == 'apt':
        return sequence([
            run_from_args(['su', 'root', '-c', ['apt-get', 'update']]),
            run_from_args([
                'su', 'root', '-c', ['apt-get', '-y', 'install', 'sudo']
            ]),
        ])
    else:
        raise UnsupportedDistribution()


def task_cli_pkg_test():
    """
    Check that the CLI is working.
    """
    return run_from_args(['flocker-deploy', '--version'])


def wipe_yum_cache(repository):
    """
    Force yum to update the metadata for a particular repository.

    :param bytes repository: The name of the repository to clear.
    """
    return run_from_args([
        b"yum",
        b"--disablerepo=*",
        b"--enablerepo=" + repository,
        b"clean",
        b"expire-cache"
    ])


def install_commands_yum(package_name, distribution, package_source,
                         base_url):
    """
    Install Flocker package on CentOS.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param str package_name: The name of the package to install.
    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.
    :param base_url: URL of repository, or ``None`` if we're not using
        development branch.

    :return: a sequence of commands to run on the distribution
    """
    commands = [
        # If package has previously been installed, 'yum install' fails,
        # so check if it is installed first.
        run(
            command="yum list installed clusterhq-release || yum install -y {0}".format(  # noqa
                get_repository_url(
                    distribution=distribution,
                    flocker_version=get_installable_version(version)))),
    ]

    if base_url is not None:
        repo = dedent(b"""\
            [clusterhq-build]
            name=clusterhq-build
            baseurl=%s
            gpgcheck=0
            enabled=0
            # There is a distinct clusterhq-build repository for each branch.
            # The metadata across these different repositories varies.  Version
            # numbers are not comparable.  A version which exists in one likely
            # does not exist in another.  In order to support switching between
            # branches (and therefore between clusterhq-build repositories),
            # tell yum to always update metadata for this repository.
            metadata_expire=0
            """) % (base_url,)
        commands.append(put(content=repo,
                            path='/tmp/clusterhq-build.repo'))
        commands.append(run_from_args([
            'cp', '/tmp/clusterhq-build.repo',
            '/etc/yum.repos.d/clusterhq-build.repo']))
        repo_options = ['--enablerepo=clusterhq-build']
    else:
        repo_options = get_repo_options(
            flocker_version=get_installable_version(version))

    if package_source.os_version:
        package_name += '-%s' % (package_source.os_version,)

    # Install package and all dependencies:

    commands.append(run_from_args(
        ["yum", "install"] + repo_options + ["-y", package_name]))

    return sequence(commands)


def install_commands_ubuntu(package_name, distribution, package_source,
                            base_url):
    """
    Install Flocker package on Ubuntu.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.
    :param base_url: URL of repository, or ``None`` if we're not using
        development branch.

    :return: a sequence of commands to run on the distribution
    """
    commands = [
        # Minimal images often have cleared apt caches and are missing
        # packages that are common in a typical release.  These commands
        # ensure that we start from a good base system with the required
        # capabilities, particularly that the add-apt-repository command
        # is available, and HTTPS URLs are supported.
        run_from_args(["apt-get", "update"]),
        run_from_args([
            "apt-get", "-y", "install", "apt-transport-https",
            "software-properties-common"]),

        # Add ClusterHQ repo for installation of Flocker packages.
        run(command='add-apt-repository -y "deb {} /"'.format(
            get_repository_url(
                distribution=distribution,
                flocker_version=get_installable_version(version))))
        ]

    if base_url is not None:
        # Add BuildBot repo for running tests
        commands.append(run_from_args([
            "add-apt-repository", "-y", "deb {} /".format(base_url)]))
        # During a release, the ClusterHQ repo may contain packages with
        # a higher version number than the Buildbot repo for a branch.
        # Use a pin file to ensure that any Buildbot repo has higher
        # priority than the ClusterHQ repo.  We only add the Buildbot
        # repo when a branch is specified, so it wil not interfere with
        # attempts to install a release (when no branch is specified).
        buildbot_host = urlparse(package_source.build_server).hostname
        commands.append(put(dedent('''\
            Package: *
            Pin: origin {}
            Pin-Priority: 700
        '''.format(buildbot_host)), '/tmp/apt-pref'))
        commands.append(run_from_args([
            'mv', '/tmp/apt-pref', '/etc/apt/preferences.d/buildbot-700']))

    # Update to read package info from new repos
    commands.append(run_from_args(["apt-get", "update"]))

    if package_source.os_version:
        # Set the version of the top-level package
        package_name += '=%s' % (package_source.os_version,)

        # If a specific version is required, ensure that the version for
        # all ClusterHQ packages is consistent.  This prevents conflicts
        # between the top-level package, which may depend on a lower
        # version of a dependency, and apt, which wants to install the
        # most recent version.  Note that this trumps the Buildbot
        # pinning above.
        commands.append(put(dedent('''\
            Package: clusterhq-*
            Pin: version {}
            Pin-Priority: 900
        '''.format(package_source.os_version)), '/tmp/apt-pref'))
        commands.append(run_from_args([
            'mv', '/tmp/apt-pref', '/etc/apt/preferences.d/clusterhq-900']))

    # Install package and all dependencies
    commands.append(run_from_args([
        'apt-get', '-y', '--force-yes', 'install', package_name]))

    return sequence(commands)


def task_package_install(package_name, distribution,
                         package_source=PackageSource()):
    """
    Install Flocker package on a distribution.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param str package_name: The name of the package to install.
    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :return: a sequence of commands to run on the distribution
    """
    if package_source.branch:
        # A development branch has been selected - add its Buildbot repo
        result_path = posixpath.join(
            '/results/omnibus/', package_source.branch, distribution)
        base_url = urljoin(package_source.build_server, result_path)
    else:
        base_url = None

    if is_centos(distribution):
        installer = install_commands_yum
    elif is_ubuntu(distribution):
        installer = install_commands_ubuntu
    else:
        raise UnsupportedDistribution()
    return installer(package_name, distribution, package_source,
                     base_url)


def task_cli_pkg_install(distribution, package_source=PackageSource()):
    """
    Install the Flocker CLI package.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :return: a sequence of commands to run on the distribution
    """
    commands = task_package_install("clusterhq-flocker-cli", distribution,
                                    package_source)
    # Although client testing is currently done as root.e want to use
    # sudo for better documentation output.
    return sequence([
        (Effect(Sudo(command=e.intent.command,
                     log_command_filter=e.intent.log_command_filter))
         if isinstance(e.intent, Run) else e)
        for e in commands.intent.effects])


PIP_CLI_PREREQ_APT = [
    'gcc',
    'libffi-dev',
    'libssl-dev',
    'python2.7',
    'python2.7-dev',
    'python-virtualenv',
]

PIP_CLI_PREREQ_YUM = [
    'gcc',
    'libffi-devel',
    'openssl-devel',
    'python',
    'python-devel',
    'python-virtualenv',
]


def task_cli_pip_prereqs(package_manager):
    """
    Install the pre-requisites for pip installation of the Flocker client.

    :param bytes package_manager: The package manager (apt, dnf, yum).
    :return: an Effect to install the pre-requisites.
    """
    if package_manager in ('dnf', 'yum'):
        return sudo_from_args(
            [package_manager, '-y', 'install'] + PIP_CLI_PREREQ_YUM
        )
    elif package_manager == 'apt':
        return sequence([
            sudo_from_args(['apt-get', 'update']),
            sudo_from_args(['apt-get', '-y', 'install'] + PIP_CLI_PREREQ_APT),
        ])
    else:
        raise UnsupportedDistribution()


def task_cli_pip_install(
        venv_name='flocker-client', package_source=PackageSource()):
    """
    Install the Flocker client into a virtualenv using pip.

    :param bytes venv_name: Name for the virtualenv.
    :param package_source: Package source description
    :return: an Effect to install the client.
    """
    vers = package_source.version
    if vers is None:
        vers = version
    url = (
        'https://{bucket}.s3.amazonaws.com/{key}/'
        'Flocker-{version}-py2-none-any.whl'.format(
            bucket=ARCHIVE_BUCKET, key='python',
            version=get_installable_version(vers))
        )
    return sequence([
        run_from_args(
            ['virtualenv', '--python=/usr/bin/python2.7', venv_name]),
        run_from_args(['source', '{}/bin/activate'.format(venv_name)]),
        run_from_args(['pip', 'install', '--upgrade', 'pip']),
        run_from_args(
            ['pip', 'install', url]),
        ])


def task_cli_pip_test(venv_name='flocker-client'):
    """
    Test the Flocker client installed in a virtualenv.

    :param bytes venv_name: Name for the virtualenv.
    :return: an Effect to test the client.
    """
    return sequence([
        run_from_args(['source', '{}/bin/activate'.format(venv_name)]),
        run_from_args(
            ['flocker-deploy', '--version']),
        ])


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
    if is_centos(distribution):
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


def task_install_api_certificates(api_cert, api_key):
    """
    Install certificate and private key required by Docker plugin to
    access the Flocker REST API.

    :param FilePath api_cert: Path to API certificate on local machine.
    :param FilePath api_key: Path to API private key local machine.
    """
    # Be better if permissions were correct from the start.
    # https://clusterhq.atlassian.net/browse/FLOC-1922
    return sequence([
        run('mkdir -p /etc/flocker'),
        run('chmod u=rwX,g=,o= /etc/flocker'),
        put(path="/etc/flocker/plugin.crt",
            content=api_cert.getContent()),
        put(path="/etc/flocker/plugin.key",
            content=api_key.getContent(),
            log_content_filter=_remove_private_key),
        ])


def task_enable_docker(distribution):
    """
    Configure docker.

    We don't actually start it (or on Ubuntu, restart it) at this point
    since the certificates it relies on have yet to be installed.
    """
    # Use the Flocker node TLS certificate, since it's readily
    # available.
    docker_tls_options = (
        '--tlsverify --tlscacert=/etc/flocker/cluster.crt'
        ' --tlscert=/etc/flocker/node.crt --tlskey=/etc/flocker/node.key'
        ' -H=0.0.0.0:2376')

    if is_centos(distribution):
        conf_path = (
            "/etc/systemd/system/docker.service.d/01-TimeoutStartSec.conf"
        )
        return sequence([
            # Give Docker a long time to start up.  On the first start, it
            # initializes a 100G filesystem which can take a while.  The
            # default startup timeout is frequently too low to let this
            # complete.
            run("mkdir -p /etc/systemd/system/docker.service.d"),
            put(
                path=conf_path,
                content=dedent(
                    """\
                    [Service]
                    TimeoutStartSec=10min
                    """
                ),
            ),
            put(path="/etc/systemd/system/docker.service.d/02-TLS.conf",
                content=dedent(
                    """\
                    [Service]
                    ExecStart=
                    ExecStart=/usr/bin/docker daemon -H fd:// {}
                    """.format(docker_tls_options))),
            run_from_args(["systemctl", "enable", "docker.service"]),
        ])
    elif distribution == 'ubuntu-14.04':
        return sequence([
            put(path="/etc/default/docker",
                content=(
                    'DOCKER_OPTS="-H unix:///var/run/docker.sock {}"'.format(
                        docker_tls_options))),
            ])
    else:
        raise DistributionNotSupported(distribution=distribution)


def open_firewalld(service):
    """
    Open firewalld port for a service.

    :param str service: Name of service.
    """
    return sequence([run_from_args(['firewall-cmd', '--reload'])] + [
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
    if is_centos(distribution):
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


def task_enable_docker_plugin(distribution):
    """
    Enable the Flocker Docker plugin.

    :param bytes distribution: The distribution name.
    """
    if is_centos(distribution):
        return sequence([
            run_from_args(['systemctl', 'enable', 'flocker-docker-plugin']),
            run_from_args(['systemctl', START, 'flocker-docker-plugin']),
            run_from_args(['systemctl', START, 'docker']),
        ])
    elif distribution == 'ubuntu-14.04':
        return sequence([
            run_from_args(['service', 'flocker-docker-plugin', 'restart']),
            run_from_args(['service', 'docker', 'restart']),
        ])
    else:
        raise DistributionNotSupported(distribution=distribution)


def task_open_control_firewall(distribution):
    """
    Open the firewall for flocker-control.
    """
    if is_centos(distribution):
        upload = put(path="/usr/lib/firewalld/services/docker.xml",
                     content=dedent(
                         """\
                         <?xml version="1.0" encoding="utf-8"?>
                         <service>
                         <short>Docker API Port</short>
                         <description>The Docker API, over TLS.</description>
                         <port protocol="tcp" port="2376"/>
                         </service>
                         """))
        open_firewall = open_firewalld
    elif distribution == 'ubuntu-14.04':
        upload = put(path="/etc/ufw/applications.d/docker",
                     content=dedent(
                         """
                         [docker]
                         title=Docker API
                         description=Docker API.
                         ports=2376/tcp
                         """))
        open_firewall = open_ufw
    else:
        raise DistributionNotSupported(distribution=distribution)

    return sequence([upload] + [
        open_firewall(service)
        for service in ['flocker-control-api', 'flocker-control-agent',
                        'docker']
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
    if is_centos(distribution):
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
        # XXX - See FLOC-3018
        run('ZFS_MODULE_LOADING=yes '
            'zpool create flocker /var/opt/flocker/pool-vdev'),
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

    elif is_centos(distribution):
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
    def maybe_disable(unit):
        return run(
            u"{{ "
            u"systemctl is-enabled {unit} && "
            u"systemctl stop {unit} && "
            u"systemctl disable {unit} "
            u"; }} || /bin/true".format(unit=unit).encode("ascii")
        )

    return sequence(
        list(
            # XXX There should be uninstall hooks for stopping services.
            maybe_disable(unit) for unit in [
                u"flocker-control", u"flocker-dataset-agent",
                u"flocker-container-agent", u"flocker-docker-plugin",
            ]
        ) + [
            run_from_args([
                b"yum", b"erase", b"-y", b"clusterhq-python-flocker",
            ]),
            # Force yum to update the metadata for the release repositories.
            # If we are running tests against a release, it is likely that the
            # metadata will not have expired for them yet.
            wipe_yum_cache(repository="clusterhq"),
            wipe_yum_cache(repository="clusterhq-testing"),
            run_from_args([
                b"yum", b"erase", b"-y", b"clusterhq-release",
            ]),
        ]
    )


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


def task_install_docker(distribution):
    """
    Return an ``Effect`` for installing Docker if it is not already installed.

    The state of ``https://get.docker.com/`` at the time the task is run
    determines the version of Docker installed.

    The version of Docker is allowed to float this way because:

    * Docker development is currently proceeding at a rapid pace.  There are
    frequently compelling reasons to want to run Docker 1.(X+1) instead of 1.X.

    * https://get.docker.com/ doesn't keep very old versions of Docker around.
    Pinning a particular version makes it laborious to rely on this source for
    Docker packages (due to the pinned version frequently disappearing from the
    repository).

    * Other package repositories frequently only have older packages available.

    * Different packagers of Docker give the package different names.  The
    different package names make it more difficult to request a specific
    version.

    * Different packagers apply different system-specific patches.  Users may
    have reasons to prefer packages from one packager over another.  Thus if
    Docker is already installed, no matter what version it is, the requirement
    is considered satisfied (we treat the user as knowing what they're doing).
    """
    if is_centos(distribution):
        # The Docker packages don't declare all of their dependencies.  They
        # seem to work on an up-to-date system, though, so make sure the system
        # is up to date.
        update = b"yum --assumeyes update && "
    else:
        update = b""

    return run(command=(
        b"[[ -e /usr/bin/docker ]] || { " + update +
        b"curl https://get.docker.com/ > /tmp/install-docker.sh && "
        b"sh /tmp/install-docker.sh"
        b"; }"
    ))


def task_install_flocker(
    distribution=None,
    package_source=PackageSource(),
):
    """
    Install flocker cluster on a distribution.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :raises: ``UnsupportedDistribution`` if the distribution is unsupported.
    """
    return task_package_install(
        "clusterhq-flocker-node",
        distribution, package_source,
    )


def task_install_docker_plugin(
    distribution=None,
    package_source=PackageSource(),
):
    """
    Install flocker docker plugin on a distribution.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :raises: ``UnsupportedDistribution`` if the distribution is unsupported.
    """
    return task_package_install(
        "clusterhq-flocker-docker-plugin",
        distribution, package_source,
    )


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
    if is_centos(distribution):
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
    commands.append(task_install_docker(distribution))
    commands.append(
        task_install_flocker(
            package_source=package_source, distribution=distribution))
    commands.append(
        task_install_docker_plugin(
            package_source=package_source, distribution=distribution))
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
    return parallel(list(
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
        task=lambda node: sequence([
            task_install_flocker(
                distribution=node.distribution,
                package_source=package_source,
            ),
            task_install_docker_plugin(
                distribution=node.distribution,
                package_source=package_source,
            )
        ]),
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
        parallel([
            sequence([
                run_remotely(
                    username='root',
                    address=node.address,
                    commands=sequence([
                        task_install_node_certificates(
                            cluster.certificates.cluster.certificate,
                            certnkey.certificate,
                            certnkey.key),
                        task_install_api_certificates(
                            cluster.certificates.user.certificate,
                            cluster.certificates.user.key),
                        task_enable_docker(node.distribution),
                        task_configure_flocker_agent(
                            control_node=cluster.control_node.address,
                            dataset_backend=cluster.dataset_backend,
                            dataset_backend_configuration=(
                                dataset_backend_configuration
                            ),
                        ),
                        task_enable_docker_plugin(node.distribution),
                        task_enable_flocker_agent(
                            distribution=node.distribution,
                        )]),
                    ),
            ]) for certnkey, node
            in zip(cluster.certificates.nodes, cluster.agent_nodes)
        ])
    ])
