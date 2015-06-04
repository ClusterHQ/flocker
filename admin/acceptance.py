# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Run the acceptance tests.
"""

import sys
import os
import yaml
from pipes import quote as shell_quote
from tempfile import mkdtemp

from zope.interface import Interface, implementer
from characteristic import attributes
from eliot import add_destination, writeFailure
from pyrsistent import pvector

from twisted.internet.error import ProcessTerminated
from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python.reflect import prefixedMethodNames

from effect import parallel
from effect.twisted import perform

from admin.vagrant import vagrant_version
from flocker.common.version import make_rpm_version
from flocker.provision import PackageSource, Variants, CLOUD_PROVIDERS
import flocker
from flocker.provision._ssh import (
    run_remotely)
from flocker.provision._install import (
    ManagedNode,
    task_pull_docker_images,
    configure_cluster,
    configure_zfs,
)
from flocker.provision._ca import Certificates
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
    """
    Return a dictionary of environment varibles describing a cluster for
    accetpance testing.

    :param Cluster cluster: Description of the cluster to get environment
        variables for.
    """
    return {
        'FLOCKER_ACCEPTANCE_CONTROL_NODE': cluster.control_node.address,
        'FLOCKER_ACCEPTANCE_AGENT_NODES':
            ':'.join(node.address for node in cluster.agent_nodes),
        'FLOCKER_ACCEPTANCE_VOLUME_BACKEND': cluster.dataset_backend.name,
        'FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH':
            cluster.certificates_path.path,
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


@implementer(IClusterRunner)
class ManagedRunner(object):
    """
    An ``IClusterRunner`` implementation that doesn't start or stop nodes but
    only gives out access to nodes that are already running and managed by
    someone else.
    """
    def __init__(self, node_addresses, distribution):
        self._nodes = pvector(
            ManagedNode(address=address, distribution=distribution)
            for address in node_addresses
        )

    def start_cluster(self, reactor):
        """
        Don't start any nodes.  Give back the addresses of the configured,
        already-started nodes.
        """
        return configured_cluster_for_nodes(reactor, self._nodes)

    def stop_cluster(self, reactor):
        """
        Don't stop any nodes.
        """
        return succeed(None)


def configured_cluster_for_nodes(reactor, nodes):
    """
    Get a ``Cluster`` with Flocker services running on the right nodes.

    Generate new certificates for the services.

    :param reactor: The reactor.
    :param nodes: The ``ManagedNode``s on which to operate.
    :returns: A ``Deferred`` which fires with ``Cluster`` when it is
        configured.
    """
    certificates_path = FilePath(mkdtemp())
    print("Generating certificates in: {}".format(certificates_path.path))
    certificates = Certificates.generate(
        certificates_path,
        nodes[0].address,
        len(nodes)
    )
    cluster = Cluster(
        all_nodes=nodes,
        control_node=nodes[0],
        agent_nodes=nodes,
        dataset_backend=DatasetBackend.zfs,
        certificates_path=certificates_path,
        certificates=certificates
    )

    configuring = perform(
        make_dispatcher(reactor),
        configure_cluster(cluster)
    )
    configuring.addCallback(lambda ignored: cluster)
    return configuring


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

    NODE_ADDRESSES = ["172.16.255.250", "172.16.255.251"]

    def __init__(self):
        self.vagrant_path = self.top_level.descendant([
            'admin', 'vagrant-acceptance-targets', self.distribution,
        ])
        self.certificates_path = self.top_level.descendant([
            'vagrant', 'tutorial', 'credentials'])
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

        nodes = pvector(
            ManagedNode(address=address, distribution=self.distribution)
            for address in self.NODE_ADDRESSES
        )

        certificates = Certificates(self.certificates_path)

        cluster = Cluster(
            all_nodes=nodes,
            control_node=nodes[0],
            agent_nodes=nodes,
            dataset_backend=DatasetBackend.zfs,
            certificates_path=self.certificates_path,
            certificates=certificates
        )

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
            all_nodes=pvector(self.nodes),
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


class RunOptions(Options):
    description = "Run the acceptance tests."

    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of {}.'.format(', '.join(DISTRIBUTIONS))],
        ['provider', None, 'vagrant',
         'The target provider to test against. '
         'One of {}.'],
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
        self.docs['provider'] = self.docs['provider'].format(
            self._get_provider_names()
        )
        self.top_level = top_level
        self['variants'] = []

    def _get_provider_names(self):
        """
        Find the names of all supported "providers" (eg Vagrant, Rackspace).

        :return: A ``list`` of ``str`` giving all such names.
        """
        return prefixedMethodNames(self.__class__, "_runner_")

    def opt_variant(self, arg):
        """
        Specify a variant of the provisioning to run.

        Supported variants: distro-testing, docker-head, zfs-testing.
        """
        self['variants'].append(Variants.lookupByValue(arg))

    def parseArgs(self, *trial_args):
        self['trial-args'] = trial_args

    def dataset_backend(self):
        """
        Get the storage driver the acceptance testing nodes will use.

        :return: A constant from ``DatasetBackend`` matching the name of the
            backend chosen by the command-line options.
        """
        try:
            return DatasetBackend.lookupByName(self['dataset-backend'])
        except ValueError:
            raise UsageError(
                "Unknown dataset backend: {}".format(
                    self['dataset-backend']
                )
            )

    def postOptions(self):
        if self['distribution'] is None:
            raise UsageError("Distribution required.")

        if self['config-file'] is not None:
            config_file = FilePath(self['config-file'])
            self['config'] = yaml.safe_load(config_file.getContent())
        else:
            self['config'] = {}

        provider = self['provider'].lower()
        provider_config = self['config'].get(provider, {})

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

        try:
            get_runner = getattr(self, "_runner_" + provider.upper())
        except AttributeError:
            raise UsageError(
                "Provider {!r} not supported. Available providers: {}".format(
                    provider, ', '.join(
                        name.lower() for name in self._get_provider_names()
                    )
                )
            )
        else:
            self.runner = get_runner(
                package_source=package_source,
                dataset_backend=self.dataset_backend(),
                provider_config=provider_config,
            )

    def _provider_config_missing(self, provider):
        """
        :param str provider: The name of the missing provider.
        :raise: ``UsageError`` indicating which provider configuration was
                missing.
        """
        raise UsageError(
            "Configuration file must include a "
            "{!r} config stanza.".format(provider)
        )

    def _runner_VAGRANT(self, package_source,
                        dataset_backend, provider_config):
        """
        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider_config: The ``vagrant`` section of the acceptance
            testing configuration file.  Since the Vagrant runner accepts no
            configuration, this is ignored.
        :returns: ``VagrantRunner``
        """
        return VagrantRunner(
            config=self['config'],
            top_level=self.top_level,
            distribution=self['distribution'],
            package_source=package_source,
            variants=self['variants'],
        )

    def _runner_MANAGED(self, package_source, dataset_backend,
                        provider_config):
        """
        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider_config: The ``managed`` section of the acceptance
            testing configuration file.  The section of the configuration
            file should look something like:

                managed:
                  addresses:
                    - "172.16.255.240"
                    - "172.16.255.241"
                  distribution: "centos-7"
        :returns: ``ManagedRunner``.
        """
        if provider_config is None:
            self._provider_config_missing("managed")

        return ManagedRunner(
            node_addresses=provider_config['addresses'],
            # TODO LATER Might be nice if this were part of
            # provider_config. See FLOC-2078.
            distribution=self['distribution'],
        )

    def _libcloud_runner(self, package_source, dataset_backend,
                         provider, provider_config):
        """
        Run some nodes using ``libcloud``.

        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider: The name of the cloud provider of nodes for the tests.
        :param provider_config: The ``managed`` section of the acceptance
        :returns: ``LibcloudRunner``.
        """
        if provider_config is None:
            self._provider_config_missing(provider)

        cloud_config = provider_config.copy()
        provisioner = CLOUD_PROVIDERS[provider](**cloud_config)
        return LibcloudRunner(
            config=self['config'],
            top_level=self.top_level,
            distribution=self['distribution'],
            package_source=package_source,
            provisioner=provisioner,
            dataset_backend=dataset_backend,
            variants=self['variants'],
        )

    def _runner_RACKSPACE(self, package_source, dataset_backend,
                          provider_config):
        """
        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider_config: The ``rackspace`` section of the acceptance
            testing configuration file.  The section of the configuration
            file should look something like:

               rackspace:
                 region: <rackspace region, e.g. "iad">
                 username: <rackspace username>
                 key: <access key>
                 keyname: <ssh-key-name>

        :see: :ref:`acceptance-testing-rackspace-config`
        """
        return self._libcloud_runner(
            package_source, dataset_backend, "rackspace", provider_config
        )

    def _runner_AWS(self, package_source, dataset_backend,
                    provider_config):
        """
        :param PackageSource package_source: The source of omnibus packages.
        :param DatasetBackend dataset_backend: A ``DatasetBackend`` constant.
        :param provider_config: The ``aws`` section of the acceptance testing
            configuration file.  The section of the configuration file should
            look something like:

               aws:
                 region: <aws region, e.g. "us-west-2">
                 access_key: <aws access key>
                 secret_access_token: <aws secret access token>
                 keyname: <ssh-key-name>
                 security_groups: ["<permissive security group>"]

        :see: :ref:`acceptance-testing-aws-config`
        """
        return self._libcloud_runner(
            package_source, dataset_backend, "aws", provider_config
        )

MESSAGE_FORMATS = {
    "flocker.provision.ssh:run":
        "[%(username)s@%(address)s]: Running %(command)s\n",
    "flocker.provision.ssh:run:output":
        "[%(username)s@%(address)s]: %(line)s\n",
    "admin.runner:run:output":
        "%(line)s\n",
}
ACTION_START_FORMATS = {
    "admin.runner:run":
        "Running %(command)s\n",
}


def eliot_output(message):
    """
    Write pretty versions of eliot log messages to stdout.
    """
    message_type = message.get('message_type')
    action_type = message.get('action_type')
    action_status = message.get('action_status')

    format = ''
    if message_type is not None:
        format = MESSAGE_FORMATS.get(message_type, '')
    elif action_type is not None:
        if action_status == 'started':
            format = ACTION_START_FORMATS.get('action_type', '')
        # We don't consider other status, since we
        # have no meaningful messages to write.
    sys.stdout.write(format % message)
    sys.stdout.flush()


def capture_journal(reactor, host, output_file):
    """
    SSH into given machine and capture relevant logs, writing them to
    output file.

    :param reactor: The reactor.
    :param bytes host: Machine to SSH into.
    :param file output_file: File to write to.
    """
    ran = run(reactor, [
        b"ssh",
        b"-C",  # compress traffic
        b"-q",  # suppress warnings
        b"-l", 'root',
        # We're ok with unknown hosts.
        b"-o", b"StrictHostKeyChecking=no",
        # The tests hang if ControlMaster is set, since OpenSSH won't
        # ever close the connection to the test server.
        b"-o", b"ControlMaster=no",
        # Some systems (notably Ubuntu) enable GSSAPI authentication which
        # involves a slow DNS operation before failing and moving on to a
        # working mechanism.  The expectation is that key-based auth will
        # be in use so just jump straight to that.
        b"-o", b"PreferredAuthentications=publickey",
        host,
        ' '.join(map(shell_quote, [
            b'journalctl',
            b'--lines', b'0',
            b'--follow',
            # Only bother with units we care about:
            b'-u', b'docker',
            b'-u', b'flocker-control',
            b'-u', b'flocker-dataset-agent',
            b'-u', b'flocker-container-agent',
        ])),
    ], handle_line=lambda line: output_file.write(line + b'\n'))
    ran.addErrback(writeFailure)


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

    from flocker.common.script import eliot_logging_service
    log_file = open("%s.log" % base_path.basename(), "a")
    log_writer = eliot_logging_service(
        log_file=log_file,
        reactor=reactor,
        capture_stdout=False)
    log_writer.startService()
    reactor.addSystemEventTrigger(
        'before', 'shutdown', log_writer.stopService)

    cluster = None
    try:
        cluster = yield runner.start_cluster(reactor)

        if options['distribution'] in ('fedora-20', 'centos-7'):
            remote_logs_file = open("remote_logs.log", "a")
            for node in cluster.all_nodes:
                capture_journal(reactor, node.address, remote_logs_file)

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
        if not options['keep']:
            runner.stop_cluster(reactor)
        else:
            print "--keep specified, not destroying nodes."
            if cluster is None:
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
