# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Run the acceptance tests.
"""

import sys
import os
import yaml

from zope.interface import Interface, implementer
from characteristic import attributes
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
)

from flocker.provision._ssh._fabric import dispatcher
from flocker.provision._effect import sequence
from effect import sync_perform as perform

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


def run_tests(reactor, nodes, control_node, agent_nodes, trial_args):
    """
    Run the acceptance tests.

    :param list nodes: The list of nodes to run the acceptance tests against.
    :param bytes control_node: The address of the control node to run API
        acceptance tests against.
    :param list agent_nodes: The list of nodes running flocker agent, to run
        API acceptance tests against.
    :param list trial_args: Arguments to pass to trial. If not
        provided, defaults to ``['flocker.acceptance']``.

    :return int: The exit-code of trial.
    """
    if not trial_args:
        trial_args = ['flocker.acceptance']

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
            FLOCKER_ACCEPTANCE_NODES=':'.join(nodes),
            FLOCKER_ACCEPTANCE_CONTROL_NODE=control_node,
            FLOCKER_ACCEPTANCE_AGENT_NODES=':'.join(agent_nodes),
        )).addCallbacks(
            callback=lambda _: 0,
            errback=check_result,
            )


class INodeRunner(Interface):
    """
    Interface for starting and stopping nodes for acceptance testing.
    """

    def start_nodes(reactor):
        """
        Start nodes for running acceptance tests.

        :param reactor: Reactor to use.
        :return Deferred: Deferred which fires with a list of nodes to run
            tests against.
        """

    def stop_nodes(reactor):
        """
        Stop the nodes started by `start_nodes`.

        :param reactor: Reactor to use.
        :return Deferred: Deferred which fires when the nodes have been
            stopped.
        """


RUNNER_ATTRIBUTES = [
    'distribution', 'top_level', 'config', 'package_source', 'variants'
]


@implementer(INodeRunner)
@attributes(RUNNER_ATTRIBUTES, apply_immutable=True)
class VagrantRunner(object):
    """
    Start and stop vagrant nodes for acceptance testing.

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
            raise UsageError("Unsupored varianta: %s."
                             % (', '.join(self.variants),))

    @inlineCallbacks
    def start_nodes(self, reactor):
        # Destroy the box to begin, so that we are guaranteed
        # a clean build.
        yield run(
            reactor,
            ['vagrant', 'destroy', '-f'],
            path=self.vagrant_path.path)

        box_version = vagrant_version(self.package_source.version)
        # Boot the VMs
        yield run(
            reactor,
            ['vagrant', 'up'],
            path=self.vagrant_path.path,
            env=extend_environ(FLOCKER_BOX_VERSION=box_version))

        for node in self.NODE_ADDRESSES:
            yield remove_known_host(reactor, node)
            yield perform(
                dispatcher,
                run_remotely(
                    username='root',
                    address=node,
                    commands=task_pull_docker_images()
                ),
            )

        returnValue(self.NODE_ADDRESSES)

    def stop_nodes(self, reactor):
        return run(
            reactor,
            ['vagrant', 'destroy', '-f'],
            path=self.vagrant_path.path)


@attributes(RUNNER_ATTRIBUTES + [
    'provisioner'
], apply_immutable=True)
class LibcloudRunner(object):
    """
    Run the tests against rackspace nodes.
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
    def start_nodes(self, reactor):
        """
        Provision cloud nodes for acceptance tests.

        :return list: List of addresses of nodes to connect to, for acceptance
            tests.
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

        commands = sequence([
            node.provision(package_source=self.package_source,
                           variants=self.variants)
            for node in self.nodes
        ])
        yield perform(dispatcher, commands)

        returnValue([node.address for node in self.nodes])

    def stop_nodes(self, reactor):
        """
        Deprovision the nodes provisioned by ``start_nodes``.
        """
        for node in self.nodes:
            try:
                print "Destroying %s" % (node.name,)
                node.destroy()
            except Exception as e:
                print "Failed to destroy %s: %s" % (node.name, e)


PROVIDERS = tuple(sorted(['vagrant'] + CLOUD_PROVIDERS.keys()))


class RunOptions(Options):
    description = "Run the acceptance tests."

    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of fedora-20.'],
        ['provider', None, 'vagrant',
         'The target provider to test against. '
         'One of {}.'.format(', '.join(PROVIDERS))],
        ['config-file', None, None,
         'Configuration for providers.'],
        ['branch', None, None, 'Branch to grab RPMS from'],
        ['flocker-version', None, flocker.__version__,
         'Version of flocker to install'],
        ['flocker-version', None, flocker.__version__,
         'Version of flocker to install'],
        ['build-server', None, 'http://build.clusterhq.com/',
         'Base URL of build server to download RPMs from'],
    ]

    optFlags = [
        ["keep", "k", "Keep VMs around, if the tests fail."],
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


@inlineCallbacks
def main(reactor, args, base_path, top_level):
    """
    :param reactor: Reactor to use.
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the flocker repository.
    """
    options = RunOptions(top_level=top_level)

    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    runner = options.runner

    try:
        nodes = yield runner.start_nodes(reactor)
        yield perform(
            dispatcher,
            configure_cluster(control_node=nodes[0], agent_nodes=nodes))
        result = yield run_tests(
            reactor=reactor,
            nodes=nodes,
            control_node=nodes[0], agent_nodes=nodes,
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
    raise SystemExit(result)
