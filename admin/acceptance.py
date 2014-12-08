#!/usr/bin/env python
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Run the acceptance tests.
"""
from subprocess import call, check_call

import sys
import os

from twisted.python.usage import Options, UsageError
from admin.vagrant import vagrant_version
import flocker
from characteristic import attributes


def extend_environ(**kwargs):
    env = os.environ.copy()
    env.update(kwargs)
    return env


def run_tests(nodes, trial_args):
    if not trial_args:
        trial_args = ['flocker.acceptance']
    return call(
        ['trial'] + trial_args,
        env=extend_environ(
            FLOCKER_ACCEPTANCE_NODES=':'.join(nodes)))


@attributes(['distribution', 'top_level'], apply_immutable=True)
class VagrantRunner(object):
    def __init__(self):
        self.vagrant_path = self.top_level.descendant([
            'admin', 'vagrant-acceptance-targets', self.distribution,
        ])
        if not self.vagrant_path.exists():
            raise UsageError("Distribution not found: %s."
                             % (self.distribution,))

    def start_nodes(self):
        """
        Start nodes for running acceptance tests.

        :return list: List of nodes to run tests against.
        """
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
                FLOCKER_BOX_VERSION=vagrant_version(flocker.__version__)))

        return ["172.16.255.240", "172.16.255.241"]

    def stop_nodes(self):
        """
        Stop the nodes started by `start_nodes`.
        """
        check_call(
            ['vagrant', 'destroy', '-f'],
            cwd=self.vagrant_path.path)


PROVIDERS = {'vagrant': VagrantRunner}


class RunOptions(Options):
    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of fedora-20.'],
        ['provider', None, 'vagrant',
         'The target provider to test against. '
         'One of vagrant.'],
    ]

    optFlags = [
        ["keep", "k", "Keep VMs around, if the tests fail."],
    ]

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

        if self['provider'] not in PROVIDERS:
            raise UsageError(
                "Provider %r not supported. Available providers: %s"
                % (self['provider'], ', '.join(PROVIDERS.keys())))

        provider_factory = PROVIDERS[self['provider']]
        self.runner = provider_factory(
            top_level=self.top_level,
            distribution=self['distribution'])


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
    if result == 0 or not options['keep']:
        runner.stop_nodes()
