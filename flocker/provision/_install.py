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
from twisted.python import log

from ._common import PackageSource

ZFS_REPO = ("https://s3.amazonaws.com/archive.zfsonlinux.org/"
            "fedora/zfs-release$(rpm -E %dist).noarch.rpm")
CLUSTERHQ_REPO = ("https://storage.googleapis.com/archive.clusterhq.com/"
                  "fedora/clusterhq-release$(rpm -E %dist).noarch.rpm")
from effect import (
    sync_performer, TypeDispatcher, ComposedDispatcher, Effect)
from effect.twisted import (
    perform, deferred_performer, make_twisted_dispatcher)
from twisted.conch.endpoints import (
    SSHCommandClientEndpoint, _NewConnectionHelper, _ReadFile, ConsoleUI)


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


def run_with_crochet(username, address, commands):
    from crochet import setup
    setup()
    from twisted.internet import reactor
    from twisted.internet.endpoints import UNIXClientEndpoint, connectProtocol
    import os
    from crochet import run_in_reactor
    from twisted.conch.ssh.keys import Key
    from twisted.python.filepath import FilePath
    key_path = FilePath(os.path.expanduser('~/.ssh/id_rsa'))
    if key_path.exists():
        keys = [Key.fromString(key_path.getContent())]
    else:
        keys = None
    try:
        agentEndpoint = UNIXClientEndpoint(
            reactor, os.environ["SSH_AUTH_SOCK"])
    except KeyError:
        agentEndpoint = None
    connection_helper = _NewConnectionHelper(
        reactor, address, 22, None, username,
        keys=keys,
        password=None,
        agentEndpoint=agentEndpoint,
        knownHosts=None, ui=ConsoleUI(lambda: _ReadFile(b"yes")))
    connection = run_in_reactor(connection_helper.secureConnection)().wait()

    from twisted.protocols.basic import LineOnlyReceiver
    from twisted.internet.defer import Deferred
    from twisted.internet.error import ConnectionDone

    @attributes(['deferred'])
    class CommandProtocol(LineOnlyReceiver, object):
        delimiter = b'\n'

        def connectionMade(self):
            self.transport.disconnecting = False

        def connectionLost(self, reason):
            if reason.check(ConnectionDone):
                self.deferred.callback(None)
            else:
                self.deferred.errback(reason)

        def lineReceived(self, line):
            log.msg(format="%(line)s",
                    system="SSH[%s@%s]" % (username, address),
                    username=username, address=address, line=line)

    def do_remote(endpoint):
        d = Deferred()
        return connectProtocol(
            endpoint, CommandProtocol(deferred=d)
            ).addCallback(lambda _: d)

    @deferred_performer
    def run(_, intent):
        log.msg(format="%(command)s",
                system="SSH[%s@%s]" % (username, address),
                username=username, address=address,
                command=intent.command)
        endpoint = SSHCommandClientEndpoint.existingConnection(
            connection, intent.command)
        return do_remote(endpoint)

    @sync_performer
    def sudo(_, intent):
        return Effect(Run(command='sudo ' + intent.command))

    @sync_performer
    def put(_, intent):
        return Effect(Run(command='echo -n %s > %s'
                                  % (shell_quote(intent.content),
                                     shell_quote(intent.path))))

    @sync_performer
    def comment(_, intent):
        pass

    dispatcher = ComposedDispatcher([
        TypeDispatcher({
            Run: run,
            Sudo: sudo,
            Put: put,
            Comment: comment,
        }),
        make_twisted_dispatcher(reactor),
    ])

    from crochet import run_in_reactor
    for command in commands:
        run_in_reactor(perform)(dispatcher, Effect(command)).wait()

    run_in_reactor(connection_helper.cleanupConnection)(
        connection, False).wait()


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


run = run_with_crochet


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


def task_disable_firewall():
    """
    Disable the firewall.
    """
    rule = ['--add-rule', 'ipv4', 'filter', 'FORWARD', '0', '-j', 'ACCEPT']
    return [
        Run.from_args(['firewall-cmd', '--permanent', '--direct'] + rule),
        Run.from_args(['firewall-cmd', '--direct'] + rule),
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
    from effect import ParallelEffects
    return [ParallelEffects(
        [Effect(Run.from_args(['docker', 'pull', image])) for image in images]
    )]


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
