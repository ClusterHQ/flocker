# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Run the client installation tests.
"""

import os
import shutil
import sys
import tempfile

from characteristic import attributes
import docker
from effect import TypeDispatcher, sync_performer, perform
from twisted.python.usage import Options, UsageError

from flocker.provision import PackageSource
from flocker.provision._effect import Sequence, perform_sequence
from flocker.provision._install import (
    ensure_minimal_setup,
    task_cli_pkg_install,
    cli_pkg_test,
    task_cli_pip_prereqs,
    task_cli_pip_install,
    cli_pip_test,
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
    'ubuntu-15.10': DockerImage(image='ubuntu:15.10', package_manager='apt'),
}

# No distribution is officially supported using pip, but the code can
# test the pip instructions using any of the images.
PIP_DISTRIBUTIONS = DOCKER_IMAGES.keys()

# Some distributions have packages created for them.
# Although CentOS 7 is not a supported client distribution, the client
# packages get built, and can be tested.
PACKAGED_CLIENT_DISTRIBUTIONS = ('centos-7', 'ubuntu-14.04', 'ubuntu-15.10')


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


class DockerContainer:
    """
    Run commands in a Docker container.
    """

    def __init__(self, image):
        # Getting Docker to work correctly on any client platform can
        # be tricky.  See
        # http://doc-dev.clusterhq.com/gettinginvolved/client-testing.html
        # for details.
        params = docker.utils.kwargs_from_env(assert_hostname=False)
        self.docker = docker.Client(version='1.16', **params)
        self.image = image

    @classmethod
    def from_distribution(cls, distribution):
        """
        Create a DockerContainer with a given distribution name.
        """
        return cls(DOCKER_IMAGES[distribution].image)

    def start(self):
        """
        Start the Docker container.
        """
        # On OS X, shared volumes must be in /Users, so use the home directory.
        # See 'Mount a host directory as a data volume' at
        # https://docs.docker.com/userguide/dockervolumes/
        self.tmpdir = tempfile.mkdtemp(dir=os.path.expanduser('~'))
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
        self.docker.remove_container(self.container_id)
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
        ['flocker-version', None, None, 'Flocker version to install'],
        ['build-server', None, 'http://build.clusterhq.com/',
         'Base URL of build server for package downloads'],
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

        self['package_source'] = PackageSource(
            version=self['flocker-version'],
            branch=self['branch'],
            build_server=self['build-server'],
        )


def get_steps_pip(distribution, package_source=PackageSource()):
    """
    Get commands to run for testing client pip installation.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :return: An ``Effect`` to pass to a ``Dispatcher`` that supports
        ``Sequence``, ``Run``, ``Sudo``, ``Comment``, and ``Put``.
    """
    if distribution not in PIP_DISTRIBUTIONS:
        raise UsageError(
            "Distribution %r not supported. Available distributions: %s"
            % (distribution, ', '.join(PIP_DISTRIBUTIONS)))
    package_manager = DOCKER_IMAGES[distribution].package_manager
    virtualenv = 'flocker-client'
    steps = [
        ensure_minimal_setup(package_manager),
        task_cli_pip_prereqs(package_manager),
        task_cli_pip_install(virtualenv, package_source),
        cli_pip_test(virtualenv, package_source),
    ]
    return steps


def get_steps_pkg(distribution, package_source=PackageSource()):
    """
    Get commands to run for testing client package installation.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :return: An ``Effect`` to pass to a ``Dispatcher`` that supports
        ``Sequence``, ``Run``, ``Sudo``, ``Comment``, and ``Put``.
    """
    if distribution not in PACKAGED_CLIENT_DISTRIBUTIONS:
        raise UsageError(
            "Distribution %r not supported. Available distributions: %s"
            % (distribution, ', '.join(PACKAGED_CLIENT_DISTRIBUTIONS)))
    package_manager = DOCKER_IMAGES[distribution].package_manager
    steps = [
        ensure_minimal_setup(package_manager),
        task_cli_pkg_install(distribution, package_source),
        cli_pkg_test(package_source),
    ]
    return steps


def run_steps(container, steps, out=sys.stdout):
    """
    Run a sequence of commands in a container.

    :param DockerContainer container: Container in which to run the test.
    :param Effect steps: Steps to to run the test.
    :param file out: Stream to write output.

    :return int: Exit status of steps.
    """
    container.start()
    try:
        for commands in steps:
            status = container.execute(commands, out)
            if status != 0:
                return status
    finally:
        container.stop()
    return 0


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
    package_source = options['package_source']
    if options['pip']:
        get_steps = get_steps_pip
    else:
        get_steps = get_steps_pkg
    steps = get_steps(distribution, package_source)
    container = DockerContainer.from_distribution(distribution)
    status = run_steps(container, steps)
    sys.exit(status)
