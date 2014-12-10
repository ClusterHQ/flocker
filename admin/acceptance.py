# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Run the acceptance tests.
"""
from subprocess import call, check_call

import sys
import os
import yaml

from zope.interface import Interface, implementer
from characteristic import attributes
from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath

from admin.vagrant import vagrant_version
import flocker


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


def run_tests(nodes, trial_args):
    """
    Run the acceptances tests.

    :param list nodes: The list of nodes to run the acceptance tests against.
    :param list trial_args: Arguments to pass to trial. If not
        provided, defaults to ``['flocker.acceptance']``.
    """
    if not trial_args:
        trial_args = ['flocker.acceptance']
    return call(
        ['trial'] + trial_args,
        env=extend_environ(
            FLOCKER_ACCEPTANCE_NODES=':'.join(nodes)))


class INodeRunner(Interface):
    """
    Interface for starting and stopping nodes for acceptance testing.
    """

    def start_nodes():
        """
        Start nodes for running acceptance tests.

        :return list: List of nodes to run tests against.
        """

    def stop_nodes(self):
        """
        Stop the nodes started by `start_nodes`.
        """


RUNNER_ATTRIBUTES = [
    'distribution', 'top_level', 'config', 'flocker_version', 'branch']


@implementer(INodeRunner)
@attributes(RUNNER_ATTRIBUTES, apply_immutable=True)
class VagrantRunner(object):
    """
    Start and stop vagrant nodes for acceptance testing.

    :cvar list NODE_ADDRESSES: List of address of vagrant nodes created.
    """
    # FIXME? Should this automatically build a box locally, or download from
    # buildbot?

    NODE_ADDRESSES = ["172.16.255.240", "172.16.255.241"]

    def __init__(self):
        self.vagrant_path = self.top_level.descendant([
            'admin', 'vagrant-acceptance-targets', self.distribution,
        ])
        if not self.vagrant_path.exists():
            raise UsageError("Distribution not found: %s."
                             % (self.distribution,))

    def start_nodes(self):
        # Destroy the box to begin, so that we are guaranteed
        # a clean build.
        check_call(
            ['vagrant', 'destroy', '-f'],
            cwd=self.vagrant_path.path)

        # Boot the VMs
        check_call(
            ['vagrant', 'up'],
            cwd=self.vagrant_path.path,
            env=extend_environ(
                FLOCKER_BOX_VERSION=vagrant_version(self.flocker_version)))

        return self.NODE_ADDRESSES

    def stop_nodes(self):
        check_call(
            ['vagrant', 'destroy', '-f'],
            cwd=self.vagrant_path.path)


@attributes(RUNNER_ATTRIBUTES, apply_immutable=True)
class RackspaceRunner(object):
    """
    Runn the tests against rackspace nodes.
    """

    def __init__(self):
        if self.distribution != 'fedora-20':
            raise ValueError("Distirubtion not supported: %r."
                             % (self.distribution,))

    def start_nodes(self):
        """
        Provision rackspace nodes for acceptance tests.

        :return list: List of addresses of nodes to connect to, for acceptance
            tests.
        """
        from flocker.provision._rackspace import Rackspace
        rackspace = Rackspace(**self.config['rackspace'])

        self.nodes = []
        for index in range(2):
            print "creating", index
            node = rackspace.create_node(
                name="test-accept-%d" % (index,),
                image_name=u'Fedora 20 (Heisenbug) (PVHVM)',
            )
            node.provision(
                distribution=self.distribution,
                version=self.flocker_version,
                branch=self.branch,
            )
            self.nodes.append(node)
            del node

        return [node.address for node in self.nodes]

    def stop_nodes(self):
        """
        Deprovision the nodes provisioned by ``start_nodes``.
        """
        for node in self.nodes:
            node.destroy()


PROVIDERS = {'vagrant': VagrantRunner, 'rackspace': RackspaceRunner}


class RunOptions(Options):
    description = "Run the acceptance tests."

    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of fedora-20.'],
        ['provider', None, 'vagrant',
         'The target provider to test against. '
         'One of vagrant.'],
        ['config-file', None, None,
         'Configuration for providers.'],
        ['branch', None, None, 'Branch to grab RPMS from'],
        ['flocker-version', None, flocker.__version__,
         'Version of flocker to install'],
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

        if self['provider'] not in PROVIDERS:
            raise UsageError(
                "Provider %r not supported. Available providers: %s"
                % (self['provider'], ', '.join(PROVIDERS.keys())))

        provider_factory = PROVIDERS[self['provider']]
        self.runner = provider_factory(
            top_level=self.top_level,
            config=self['config'],
            distribution=self['distribution'],
            flocker_version=self['flocker-version'],
            branch=self['branch'],
        )


def main(args, base_path, top_level):
    """
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

    nodes = runner.start_nodes()
    result = run_tests(nodes, options['trial-args'])
    # Unless the tests failed, and the user asked to keep the nodes, we delete
    # them.
    if not (result != 0 and options['keep']):
        runner.stop_nodes()
