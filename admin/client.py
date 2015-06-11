# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Run the acceptance tests.
"""

import sys
import yaml

from zope.interface import Interface, implementer
from characteristic import attributes
from eliot import add_destination
from twisted.internet.error import ProcessTerminated
from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks, returnValue

from flocker.common.version import make_rpm_version
from flocker.provision import PackageSource, CLOUD_PROVIDERS
import flocker
from flocker.provision._ssh import (
    run_remotely)
from flocker.provision._install import (
    task_client_installation_test,
    install_cli,
)
from effect.twisted import perform
from flocker.provision._ssh._conch import make_dispatcher

from .runner import run


def remove_known_host(reactor, hostname):
    """
    Remove all keys belonging to hostname from a known_hosts file.

    :param reactor: Reactor to use.
    :param bytes hostname: Remove all keys belonging to this hostname from
        known_hosts.
    """
    return run(reactor, ['ssh-keygen', '-R', hostname])


def run_client_tests(reactor, node):
    """
    Run the client acceptance tests.

    :param INode node: The node to run client acceptance tests against.

    :return int: The exit-code of trial.
    """
    def check_result(f):
        f.trap(ProcessTerminated)
        if f.value.exitCode is not None:
            return f.value.exitCode
        else:
            return f

    return perform(make_dispatcher(reactor), run_remotely(
        username=node.get_default_username(),
        address=node.address,
        commands=task_client_installation_test()
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
    'distribution', 'top_level', 'config', 'package_source'
]


@implementer(INodeRunner)
@attributes(RUNNER_ATTRIBUTES + [
    'provisioner',
], apply_immutable=True)
class LibcloudRunner(object):
    """
    Start and stop cloud nodes for acceptance testing.

    :ivar LibcloudProvioner provisioner: The provisioner to use to create the
        nodes.
    :ivar VolumeBackend volume_backend: The volume backend the nodes are
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
    def start_nodes(self, reactor, node_count):
        """
        Start cloud nodes for client tests.

        :return list: List of addresses of nodes to connect to, for client
            tests.
        """
        metadata = {
            'purpose': 'client-testing',
            'distribution': self.distribution,
        }
        metadata.update(self.metadata)

        for index in range(node_count):
            name = "client-test-%s-%d" % (self.creator, index)
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

        returnValue(self.nodes)

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


DISTRIBUTIONS = ('centos-7', 'ubuntu-14.04', 'ubuntu-15.04')

PROVIDERS = tuple(sorted(CLOUD_PROVIDERS.keys()))


class RunOptions(Options):
    description = "Run the client tests."

    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of {}.'.format(', '.join(DISTRIBUTIONS))],
        ['provider', None, 'rackspace',
         'The target provider to test against. '
         'One of {}.'.format(', '.join(PROVIDERS))],
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
    ]

    synopsis = ('Usage: run-client-tests --distribution <distribution> '
                '[--provider <provider>]')

    def __init__(self, top_level):
        """
        :param FilePath top_level: The top-level of the flocker repository.
        """
        Options.__init__(self)
        self.top_level = top_level

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

        if self['distribution'] not in DISTRIBUTIONS:
            raise UsageError(
                "Distribution %r not supported. Available distributions: %s"
                % (self['distribution'], ', '.join(DISTRIBUTIONS)))

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
            )

from .acceptance import eliot_output


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

    try:
        nodes = yield runner.start_nodes(reactor, node_count=1)
        yield perform(
            make_dispatcher(reactor),
            install_cli(runner.package_source, nodes[0]))
        result = yield run_client_tests(reactor=reactor, node=nodes[0])
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
