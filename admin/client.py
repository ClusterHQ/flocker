# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Run the acceptance tests.
"""

import os
import sys
import tempfile
import yaml

import docker as dockerpy
from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath
from flocker.common.version import make_rpm_version
from flocker.provision import PackageSource
import flocker
from flocker.provision._install import (
    task_client_installation_test,
    task_install_cli,
)
from effect.twisted import perform

from effect import TypeDispatcher, sync_performer
from flocker.provision._effect import Sequence, perform_sequence
from flocker.provision._ssh._model import Run, Sudo, Put, Comment
from flocker.provision._ssh._conch import perform_sudo, perform_put

DOCKER_IMAGES = {
    'centos-7': 'centos:7',
    'ubuntu-14.04': 'ubuntu:14.04',
    'ubuntu-15.04': 'ubuntu:15.04',
}

DISTRIBUTIONS = DOCKER_IMAGES.keys()


class ScriptBuilder(TypeDispatcher):
    """
    Convert an Effect sequence to a shell script.

    The effects are those defined in flocker.provision._effect and
    flocker.provision._ssh._model.
    """

    def __init__(self, effects):
        self.lines = ['#!/bin/bash', 'set -e']
        TypeDispatcher.__init__(self, {
            Run: self.perform_run,
            Sudo: perform_sudo,
            Put: perform_put,
            Comment: self.perform_comment,
            Sequence: perform_sequence
        })
        perform(self, effects)
        # Add blank line to terminate script with a newline
        self.lines.append('')
        self._script = '\n'.join(self.lines)

    @sync_performer
    def perform_run(self, dispatcher, intent):
        self.lines.append(intent.command)

    @sync_performer
    def perform_comment(self, dispatcher, intent):
        self.lines.append('# ' + intent.comment)

    def script(self):
        return self._script


def make_script_file(effects):
    builder = ScriptBuilder(effects)
    fd, filename = tempfile.mkstemp(text=True)
    os.write(fd, builder.script())
    os.close(fd)
    os.chmod(filename, 0555)
    return filename


def run_script_file(docker, container_id, script):
    session = docker.exec_create(container_id, script)
    session_id = session[u'Id']
    output = docker.exec_start(session)
    status = docker.exec_inspect(session_id)[u'ExitCode']
    if status == 0:
        sys.stdout.write(output)
    else:
        sys.exit(output)


class RunOptions(Options):
    description = "Run the client tests."

    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of {}.'.format(', '.join(DISTRIBUTIONS))],
        # XXX - remove the following flag once Buildbot is updated
        ['provider', None, None, 'No longer used'],
        ['config-file', None, None,
         'Configuration for providers.'],
        ['branch', None, None, 'Branch to grab packages from'],
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

        self['package_source'] = PackageSource(
            version=self['flocker-version'],
            os_version=os_version,
            branch=self['branch'],
            build_server=self['build-server'],
        )

        if self['distribution'] not in DISTRIBUTIONS:
            raise UsageError(
                "Distribution %r not supported. Available distributions: %s"
                % (self['distribution'], ', '.join(DISTRIBUTIONS)))


def main(args, base_path, top_level):
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

    distribution = options['distribution']
    package_source = options['package_source']
    install = make_script_file(task_install_cli(distribution, package_source))
    try:
        dotest = make_script_file(task_client_installation_test())
        try:
            docker = dockerpy.Client(version='1.18')
            image = DOCKER_IMAGES[distribution]
            docker.pull(image)
            container = docker.create_container(
                image=image, command='/bin/bash', tty=True,
                volumes=['/install.sh', '/dotest.sh'],
            )
            container_id = container[u'Id']
            docker.start(
                container_id,
                binds={
                    install: {'bind': '/install.sh', 'ro': True},
                    dotest: {'bind': '/dotest.sh', 'ro': True}
                }
            )
            try:
                run_script_file(docker, container_id, '/install.sh')
                run_script_file(docker, container_id, '/dotest.sh')
            finally:
                docker.stop(container_id)
        finally:
            os.remove(dotest)
    finally:
        os.remove(install)
