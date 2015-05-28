# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Run the acceptance tests.
"""

import sys
import os
import yaml
from tempfile import mkdtemp

from zope.interface import Interface, implementer
from characteristic import attributes
from eliot import add_destination
from pyrsistent import pvector

from twisted.internet.error import ProcessTerminated
from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks, returnValue

from admin.vagrant import vagrant_version
from flocker.common.version import make_rpm_version
from flocker.provision import PackageSource, Variants, CLOUD_PROVIDERS
import flocker
from flocker.provision._ssh import (
    run_remotely)
from flocker.provision._install import (
    task_pull_docker_images,
    configure_cluster,
    configure_zfs,
)
from flocker.provision._libcloud import INode
from flocker.provision._ca import Certificates
from effect import parallel
from effect.twisted import perform
from flocker.provision._ssh._conch import make_dispatcher
from flocker.provision._common import Cluster
from flocker.acceptance.testtools import DatasetBackend

from .runner import run


def extend_environ(**kwargs):
    """
    Return a copy of ``os.environ`` with some additional environment variables
        added.

    :param **kwargs: The enviroment variables to add.
    :return dict: The new environment.
    """
    env = os.environ.copy()
    env.update(kwargs)
    return env


def remove_known_host(reactor, hostname):
    """
    Remove all keys belonging to hostname from a known_hosts file.

    :param reactor: Reactor to use.
    :param bytes hostname: Remove all keys belonging to this hostname from
        known_hosts.
    """
    return run(reactor, ['ssh-keygen', '-R', hostname])


def get_trial_environment(cluster):
    return {
        'FLOCKER_ACCEPTANCE_CONTROL_NODE': cluster.control_node.address,
        'FLOCKER_ACCEPTANCE_AGENT_NODES':
            ':'.join(node.address for node in cluster.agent_nodes),
        'FLOCKER_ACCEPTANCE_VOLUME_BACKEND': cluster.dataset_backend.name,
        'FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH': cluster.certificates_path.path,
    }


def run_tests(reactor, cluster, trial_args):
    """
    Run the acceptance tests.

    :param Cluster cluster: The cluster to run acceptance tests against.
    :param list trial_args: Arguments to pass to trial. If not
        provided, defaults to ``['flocker.acceptance']``.

    :return int: The exit-code of trial.
    """
    if not trial_args:
        trial_args = ['--rterrors', 'flocker.acceptance']

    def check_result(f):
        f.trap(ProcessTerminated)
        if f.value.exitCode is not None:
            return f.value.exitCode
        else:
            return f

    return run(
        reactor,
        ['trial'] + list(trial_args),
        env=extend_environ(
            **get_trial_environment(cluster)
        )).addCallbacks(
            callback=lambda _: 0,
            errback=check_result,
            )


class IClusterRunner(Interface):
    """
    Interface for starting and stopping a cluster for acceptance testing.
    """

    def start_cluster(reactor):
        """
        Start cluster for running acceptance tests.

        :param reactor: Reactor to use.
        :return Deferred: Deferred which fires with a cluster to run
            tests against.
        """

    def stop_cluster(reactor):
        """
        Stop the cluster started by `start_cluster`.

        :param reactor: Reactor to use.
        :return Deferred: Deferred which fires when the cluster has been
            stopped.
        """


RUNNER_ATTRIBUTES = [
    'distribution', 'top_level', 'config', 'package_source', 'variants'
]


@implementer(INode)
@attributes(['address', 'distribution'], apply_immutable=True)
class VagrantNode(object):
    """
    Node run using VagrantRunner
    """


@implementer(IClusterRunner)
@attributes(RUNNER_ATTRIBUTES, apply_immutable=True)
class VagrantRunner(object):
    """
    Start and stop vagrant cluster for acceptance testing.

    :cvar list NODE_ADDRESSES: List of address of vagrant nodes created.
    """
    # TODO: This should acquire the vagrant image automatically,
    # rather than assuming it is available.
    # https://clusterhq.atlassian.net/browse/FLOC-1163

    NODE_ADDRESSES = ["172.16.255.240", "172.16.255.241"]

    def __init__(self):
        self.vagrant_path = self.top_level.descendant([
            'admin', 'vagrant-acceptance-targets', self.distribution,
        ])
        if not self.vagrant_path.exists():
            raise UsageError("Distribution not found: %s."
                             % (self.distribution,))

        if self.variants:
            raise UsageError("Variants unsupported on vagrant.")

    @inlineCallbacks
    def start_cluster(self, reactor):
        # Destroy the box to begin, so that we are guaranteed
        # a clean build.
        yield run(
            reactor,
            ['vagrant', 'destroy', '-f'],
            path=self.vagrant_path.path)

        if self.package_source.version:
            env = extend_environ(
                FLOCKER_BOX_VERSION=vagrant_version(
                    self.package_source.version))
        else:
            env = os.environ
        # Boot the VMs
        yield run(
            reactor,
            ['vagrant', 'up'],
            path=self.vagrant_path.path,
            env=env)

        for node in self.NODE_ADDRESSES:
            yield remove_known_host(reactor, node)

        certificates_path = FilePath(mkdtemp())
        print("Generating certificates in: {}".format(certificates_path.path))
        certificates = Certificates.generate(
            certificates_path,
            self.NODE_ADDRESSES[0],
            len(self.NODE_ADDRESSES))

        nodes = pvector(
            VagrantNode(address=address, distribution=self.distribution)
            for address in self.NODE_ADDRESSES
        )
        cluster = Cluster(
            control_node=nodes[0],
            agent_nodes=nodes,
            dataset_backend=DatasetBackend.zfs,
            certificates_path=certificates_path,
            certificates=certificates)

        yield perform(make_dispatcher(reactor), configure_cluster(cluster))

        returnValue(cluster)

    def stop_cluster(self, reactor):
        return run(
            reactor,
            ['vagrant', 'destroy', '-f'],
            path=self.vagrant_path.path)


@attributes(RUNNER_ATTRIBUTES + [
    'provisioner',
    'dataset_backend',
], apply_immutable=True)
class LibcloudRunner(object):
    """
    Start and stop cloud cluster for acceptance testing.

    :ivar LibcloudProvioner provisioner: The provisioner to use to create the
        nodes.
    :ivar DatasetBackend dataset_backend: The volume backend the nodes are
        configured with.
    """

    def __init__(self):
        self.nodes = []

        self.metadata = self.config.get('metadata', {})
        try:
            creator = self.metadata['creator']
        except KeyError:
            raise UsageError("Must specify creator metadata.")

        if not creator.isalnum():
            raise UsageError(
                "Creator must be alphanumeric. Found {!r}".format(creator)
            )
        self.creator = creator

    @inlineCallbacks
    def start_cluster(self, reactor):
        """
        Provision cloud cluster for acceptance tests.

        :return Cluster: The cluster to connect to for acceptance tests.
        """
        metadata = {
            'purpose': 'acceptance-testing',
            'distribution': self.distribution,
        }
        metadata.update(self.metadata)

        for index in range(2):
            name = "acceptance-test-%s-%d" % (self.creator, index)
            try:
                print "Creating node %d: %s" % (index, name)
                node = self.provisioner.create_node(
                    name=name,
                    distribution=self.distribution,
                    metadata=metadata,
                )
            except:
                print "Error creating node %d: %s" % (index, name)
                print "It may have leaked into the cloud."
                raise

            yield remove_known_host(reactor, node.address)
            self.nodes.append(node)
            del node

        commands = parallel([
            node.provision(package_source=self.package_source,
                           variants=self.variants)
            for node in self.nodes
        ])
        if self.dataset_backend == DatasetBackend.zfs:
            zfs_commands = parallel([
                configure_zfs(node, variants=self.variants)
                for node in self.nodes
            ])
            commands = commands.on(success=lambda _: zfs_commands)

        certificates_path = FilePath(mkdtemp())
        print("Generating certificates in: {}".format(certificates_path.path))
        certificates = Certificates.generate(
            certificates_path,
            self.nodes[0].address,
            len(self.nodes))

        cluster = Cluster(
            control_node=self.nodes[0],
            agent_nodes=pvector(self.nodes),
            dataset_backend=DatasetBackend.zfs,
            certificates_path=certificates_path,
            certificates=certificates)

        commands = commands.on(success=lambda _: configure_cluster(cluster))

        yield perform(make_dispatcher(reactor), commands)

        returnValue(cluster)

    def stop_cluster(self, reactor):
        """
        Deprovision the cluster provisioned by ``start_cluster``.
        """
        for node in self.nodes:
            try:
                print "Destroying %s" % (node.name,)
                node.destroy()
            except Exception as e:
                print "Failed to destroy %s: %s" % (node.name, e)


DISTRIBUTIONS = ('centos-7', 'fedora-20', 'ubuntu-14.04')
PROVIDERS = tuple(sorted(['vagrant'] + CLOUD_PROVIDERS.keys()))


class RunOptions(Options):
    description = "Run the acceptance tests."

    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of {}.'.format(', '.join(DISTRIBUTIONS))],
        ['provider', None, 'vagrant',
         'The target provider to test against. '
         'One of {}.'.format(', '.join(PROVIDERS))],
        ['dataset-backend', None, 'zfs',
         'The dataset backend to test against. '
         'One of {}'.format(', '.join(backend.name for backend
                                      in DatasetBackend.iterconstants()))],
        ['config-file', None, None,
         'Configuration for providers.'],
        ['branch', None, None, 'Branch to grab packages from'],
        ['flocker-version', None, flocker.__version__,
         'Version of flocker to install'],
        ['flocker-version', None, flocker.__version__,
         'Version of flocker to install'],
        ['build-server', None, 'http://build.clusterhq.com/',
         'Base URL of build server for package downloads'],
    ]

    optFlags = [
        ["keep", "k", "Keep VMs around, if the tests fail."],
        ["no-pull", None,
         "Do not pull any Docker images when provisioning nodes."],
    ]

    synopsis = ('Usage: run-acceptance-tests --distribution <distribution> '
                '[--provider <provider>] [<test-cases>]')

    def __init__(self, top_level):
        """
        :param FilePath top_level: The top-level of the flocker repository.
        """
        Options.__init__(self)
        self.top_level = top_level
        self['variants'] = []

    def opt_variant(self, arg):
        """
        Specify a variant of the provisioning to run.

        Supported variants: distro-testing, docker-head, zfs-testing.
        """
        self['variants'].append(Variants.lookupByValue(arg))

    def parseArgs(self, *trial_args):
        self['trial-args'] = trial_args

    def postOptions(self):
        if self['distribution'] is None:
            raise UsageError("Distribution required.")

        try:
            self.dataset_backend = DatasetBackend.lookupByName(
                self['dataset-backend'])
        except ValueError:
            raise UsageError("Unknown dataset backend: %s"
                             % (self['dataset-backend']))

        if self['config-file'] is not None:
            config_file = FilePath(self['config-file'])
            self['config'] = yaml.safe_load(config_file.getContent())
        else:
            self['config'] = {}

        if self['flocker-version']:
            rpm_version = make_rpm_version(self['flocker-version'])
            os_version = "%s-%s" % (rpm_version.version, rpm_version.release)
            if os_version.endswith('.dirty'):
                os_version = os_version[:-len('.dirty')]
        else:
            os_version = None

        package_source = PackageSource(
            version=self['flocker-version'],
            os_version=os_version,
            branch=self['branch'],
            build_server=self['build-server'],
        )

        if self['provider'] not in PROVIDERS:
            raise UsageError(
                "Provider %r not supported. Available providers: %s"
                % (self['provider'], ', '.join(PROVIDERS)))

        if self['provider'] in CLOUD_PROVIDERS:
            # Configuration must include credentials etc for cloud providers.
            try:
                provider_config = self['config'][self['provider']]
            except KeyError:
                raise UsageError(
                    "Configuration file must include a "
                    "{!r} config stanza.".format(self['provider'])
                )

            provisioner = CLOUD_PROVIDERS[self['provider']](**provider_config)

            self.runner = LibcloudRunner(
                config=self['config'],
                top_level=self.top_level,
                distribution=self['distribution'],
                package_source=package_source,
                provisioner=provisioner,
                dataset_backend=self.dataset_backend,
                variants=self['variants'],
            )
        else:
            self.runner = VagrantRunner(
                config=self['config'],
                top_level=self.top_level,
                distribution=self['distribution'],
                package_source=package_source,
                variants=self['variants'],
            )


MESSAGE_FORMATS = {
    "flocker.provision.ssh:run":
        "[%(username)s@%(address)s]: Running %(command)s\n",
    "flocker.provision.ssh:run:output":
        "[%(username)s@%(address)s]: %(line)s\n",
    "admin.runner:run":
        "Running %(command)s\n",
    "admin.runner:run:output":
        "%(line)s\n",
}


def eliot_output(message):
    """
    Write pretty versions of eliot log messages to stdout.
    """
    message_type = message.get('message_type', message.get('action_type'))
    sys.stdout.write(MESSAGE_FORMATS.get(message_type, '') % message)
    sys.stdout.flush()


@inlineCallbacks
def main(reactor, args, base_path, top_level):
    """
    :param reactor: Reactor to use.
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the flocker repository.
    """
    options = RunOptions(top_level=top_level)

    add_destination(eliot_output)
    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    runner = options.runner

    try:
        cluster = yield runner.start_cluster(reactor)

        if not options["no-pull"]:
            yield perform(
                make_dispatcher(reactor),
                parallel([
                    run_remotely(
                        username='root',
                        address=node.address,
                        commands=task_pull_docker_images()
                    ) for node in cluster.agent_nodes
                ]),
            )

        yield perform(make_dispatcher(reactor), configure_cluster(cluster))

        result = yield run_tests(
            reactor=reactor,
            cluster=cluster,
            trial_args=options['trial-args'])
    except:
        result = 1
        raise
    finally:
        # Unless the tests failed, and the user asked to keep the nodes, we
        # delete them.
        if not (result != 0 and options['keep']):
            runner.stop_nodes(reactor)
        elif options['keep']:
            print "--keep specified, not destroying nodes."
            try:
                cluster
            except NameError:
                print ("Didn't finish creating the cluster.")
            else:
                print ("To run acceptance tests against these nodes, "
                       "set the following environment variables: ")

                environment_variables = get_trial_environment(cluster)

                for environment_variable in environment_variables:
                    print "export {name}={value};".format(
                        name=environment_variable,
                        value=environment_variables[environment_variable],
                    )

    raise SystemExit(result)
