#!/usr/bin/env python
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Run the acceptance tests.
"""
from subprocess import check_call

import sys
import os

from twisted.python import usage
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
    check_call(
        ['trial'] + trial_args,
        env=extend_environ(
            FLOCKER_ACCEPTANCE_NODES=':'.join(nodes)))


@attributes(['distribution', 'top_level'], apply_immutable=True)
class VagrantRunner(object):
    def run(self, trial_args):

        VAGRANT_PATH = self.top_level.descendant([
            'admin', 'vagrant-acceptance-targets', self.distribution,
        ])

        # Destroy the box to begin, so that we are guaranteed
        # a clean build.
        check_call(
            ['vagrant', 'destroy', '-f'],
            cwd=VAGRANT_PATH.path)

        # Boot the VMs
        check_call(
            ['vagrant', 'up'],
            cwd=VAGRANT_PATH.path,
            env=extend_environ(
                FLOCKER_BOX_VERSION=vagrant_version(flocker.__version__)))

        # Run the tests
        run_tests(nodes=["172.16.255.240", "172.16.255.241"],
                  trial_args=trial_args)

        # And destroy at the end to save space.  If one of the above commands
        # fail, this will be skipped, so the image can still be debugged.
        check_call(
            ['vagrant', 'destroy', '-f'],
            cwd=VAGRANT_PATH.path)


PROVIDERS = {'vagrant': VagrantRunner}


class RunOptions(usage.Options):
    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of fedora-20.'],
        ['provider', None, 'vagrant',
         'The target provider to test against. '
         'One of vagrant.'],
    ]

    def parseArgs(self, *trial_args):
        self['trial-args'] = trial_args

    def postOptions(self):
        if self['distribution'] is None:
            if self['distribution'] not in PROVIDERS:
                raise usage.UsageError("Distribution required.")

        if self['provider'] not in PROVIDERS:
            raise usage.UsageError(
                "Provider %r not supported. Available providers: %s"
                % (self['provider'], ', '.join(PROVIDERS.keys())))

        self.provider_factory = PROVIDERS[self['provider']]


def main(args, base_path, top_level):
    """
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the flocker repository.
    """
    options = RunOptions()

    try:
        options.parseOptions(args)
    except usage.UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    if options['provider'] not in PROVIDERS:
        sys.stderr.write(
            "%s: Provider %r not supported. Available providers: %s"
            % (base_path.basename(), options['provider'],
               ', '.join(options['providers'].keys())))

    runner = options.provider_factory(
        top_level=top_level,
        distribution=options['distribution'])

    runner.run(options['trial-args'])
