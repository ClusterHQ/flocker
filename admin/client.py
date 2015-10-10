# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Run the client installation tests.
"""

import os
import shutil
import sys
import tempfile
import yaml

from characteristic import attributes
import docker
from effect import TypeDispatcher, sync_performer, perform
from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath

import flocker
from flocker.provision import PackageSource
from flocker.provision._effect import Sequence, perform_sequence
from flocker.provision._install import (
    ensure_minimal_setup,
    task_cli_pkg_install,
    task_cli_pkg_test,
    task_cli_pip_prereqs,
    task_cli_pip_install,
    task_cli_pip_test,
)
from flocker.provision._ssh import (
    Run, Sudo, Put, Comment, perform_sudo, perform_put)


@attributes(['image', 'package_manager'])
class DockerImage(object):
    """Holder for Docker image information."""

DOCKER_IMAGES = {
    'centos-7': DockerImage(image='centos:7', package_manager='yum'),
    'debian-8': DockerImage(image='debian:8', package_manager='apt'),
    'fedora-22': DockerImage(image='fedora:22', package_manager='dnf'),
    'ubuntu-14.04': DockerImage(image='ubuntu:14.04', package_manager='apt'),
    'ubuntu-15.04': DockerImage(image='ubuntu:15.04', package_manager='apt'),
}

PIP_DISTRIBUTIONS = DOCKER_IMAGES.keys()
PACKAGED_CLIENT_DISTRIBUTIONS = ('ubuntu-14.04', 'ubuntu-15.04')


class ScriptBuilder(TypeDispatcher):
    """
    Convert an Effect sequence to a shell script.

    The effects are those defined in flocker.provision._effect and
    flocker.provision._ssh._model.
    """

    def __init__(self, effects):
        self.lines = [
            '#!/bin/bash',
            'set -ex'
        ]
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
        """
        For Run effects, add the command line.
        """
        self.lines.append(intent.command)

    @sync_performer
    def perform_comment(self, dispatcher, intent):
        """
        For Comment effects, prefix the comment with #
        """
        self.lines.append('# ' + intent.comment)

    def script(self):
        """
        Return the generated shell script.
        """
        return self._script


def make_script_file(dir, effects):
    """
    Create a shell script file from a sequence of effects.

    :param bytes dir: The directory in which to create the script.
    :param Effect effects: An effect which contains the commands,
        typically a Sequence containing multiple commands.
    :return: The base filename of the script.
    """
    builder = ScriptBuilder(effects)
    fd, filename = tempfile.mkstemp(dir=dir, text=True)
    os.write(fd, builder.script())
    os.close(fd)
    os.chmod(filename, 0555)
    return os.path.basename(filename)


class DockerRunner:
    """
    Run commands in a Docker container.
    """

    def __init__(self, image):
        self.docker = docker.Client(version='1.18')
        self.image = image

    def start(self):
        """
        Start the Docker container.
        """
        self.tmpdir = tempfile.mkdtemp()
        try:
            self.docker.pull(self.image)
            container = self.docker.create_container(
                image=self.image, command='/bin/bash', tty=True,
                volumes=['/mnt/script'],
            )
            self.container_id = container[u'Id']
            self.docker.start(
                self.container_id,
                binds={
                    self.tmpdir: {'bind': '/mnt/script', 'ro': True},
                }
            )
        except:
            os.rmdir(self.tmpdir)
            raise

    def stop(self):
        """
        Stop the Docker container.
        """
        self.docker.stop(self.container_id)
        shutil.rmtree(self.tmpdir)

    def execute(self, commands, out=sys.stdout):
        """
        Execute a set of commands in the Docker container.

        The set of commands provided to one call of ``execute`` will be
        executed in a single session. This means commands will see the
        environment created by previous commands.

        The output of the commands is sent to the ``out`` file object,
        which must have a ``write`` method.

        :param Effect commands: An Effect containing the commands to run,
            probably a Sequence of Effects, one for each command to run.
        :param out: Where to send command output. Any object with a
            ``write`` method.
        :return int: The exit status of the commands.  If all commands
            succeed, this will be zero. If any command fails, this will
            be non-zero.
        """
        script_file = make_script_file(self.tmpdir, commands)
        script = '/mnt/script/{}'.format(script_file)
        session = self.docker.exec_create(self.container_id, script)
        session_id = session[u'Id']
        for output in self.docker.exec_start(session, stream=True):
            out.write(output)
        return self.docker.exec_inspect(session_id)[u'ExitCode']


class RunOptions(Options):
    description = "Run the client tests."

    optParameters = [
        ['distribution', None, None,
         'The target distribution. '
         'One of {}.  With --pip, one of {}'.format(
            ', '.join(PACKAGED_CLIENT_DISTRIBUTIONS),
            ', '.join(PIP_DISTRIBUTIONS))],
        ['branch', None, None, 'Branch to grab packages from'],
        ['flocker-version', None, flocker.__version__,
         'Version of flocker to install'],
        ['build-server', None, 'http://build.clusterhq.com/',
         'Base URL of build server for package downloads'],
        # XXX - remove the remaining flags once Buildbot is updated (FLOC-2813)
        ['provider', None, None, 'No longer used.'],
        ['config-file', None, None, 'No longer used.'],
    ]

    optFlags = [
        ['pip', None, 'Install using pip rather than packages.'],
    ]

    synopsis = ('Usage: run-client-tests --distribution <distribution> '
                '[--branch <branch>] [--flocker-version <version>] '
                '[--build-server <url>] [--pip]')

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

        self['package_source'] = PackageSource(
            version=self['flocker-version'],
            branch=self['branch'],
            build_server=self['build-server'],
        )

        if self['pip']:
            supported = PIP_DISTRIBUTIONS
        else:
            supported = PACKAGED_CLIENT_DISTRIBUTIONS
        if self['distribution'] not in supported:
            raise UsageError(
                "Distribution %r not supported. Available distributions: %s"
                % (self['distribution'], ', '.join(supported)))


def main(args, base_path, top_level):
    """
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the Flocker repository.
    """
    options = RunOptions(top_level=top_level)

    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.exit("%s: %s\n" % (base_path.basename(), e))

    distribution = options['distribution']
    package_manager = DOCKER_IMAGES[distribution].package_manager
    package_source = options['package_source']
    if options['pip']:
        virtualenv = 'flocker-client'
        steps = [
            ensure_minimal_setup(package_manager),
            task_cli_pip_prereqs(package_manager),
            task_cli_pip_install(virtualenv, package_source),
            task_cli_pip_test(virtualenv),
        ]
    else:
        steps = [
            ensure_minimal_setup(package_manager),
            task_cli_pkg_install(distribution, package_source),
            task_cli_pkg_test(),
        ]
    runner = DockerRunner(DOCKER_IMAGES[distribution].image)
    runner.start()
    try:
        for commands in steps:
            status = runner.execute(commands)
            if status != 0:
                sys.exit(status)
    finally:
        runner.stop()
