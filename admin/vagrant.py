# -*- test-case-name: admin.test.test_vagrant -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tools for interacting with vagrant.
"""

import sys
import os

import json

from twisted.python import usage

import flocker

from admin.runner import run
from admin.release import make_rpm_version


class BuildOptions(usage.Options):

    optParameters = [
        ['branch', None, None, 'Branch to grab RPMS from'],
        ['box', None, None, 'Name of box to build'],
        ['flocker-version', None, flocker.__version__,
         'Version of flocker to install'],
        ['build-server', None, 'http://build.clusterhq.com/',
         'Base URL of build server to download RPMs from'],
    ]

    def __init__(self, base_path, top_level):
        """
        :param FilePath base_path: The executable being run.
        :param FilePath top_level: The top-level of the flocker repository.
        """
        usage.Options.__init__(self)
        self.base_path = base_path
        self.top_level = top_level

    def postOptions(self):
        if self.base_path.basename() == 'build':
            if self['box'] is not None:
                raise usage.UsageError(
                    "Can't specify box when invoked from box directory.")
            self['path'] = self.base_path.parent()
            self['box'] = self['path'].basename()
        else:
            if self['box'] is None:
                raise usage.UsageError(
                    "Must specify box when invoked directly.")
            self['path'] = self.top_level.descendant(['vagrant', self['box']])


def box_metadata(name, version, path):
    """
    Generate metadata for a vagrant box.

    This metadata can be used to locally(!) add the box to vagrant,
    with the correct version, for testing.

    :param bytes name: Base name of vagrant box. Used to build filename.
    :param bytes version: Version of vagrant box. Used to build filename.
    :param FilePath path: Directory containing ``Vagrantfile``.
    """
    if version:
        # Vagrant doesn't like - in version numbers.
        # It also doesn't like _ but we don't generate that.
        dotted_version = version.replace('-', '.')
    else:
        dotted_version = '0'

    metadata = {
        "name": "clusterhq/%s" % (name,),
        "description": "Test clusterhq/%s box." % (name,),
        'versions': [{
            "version": dotted_version,
            "providers": [{
                "name": "virtualbox",
                "url": path.path
            }]
        }]
    }
    return metadata


def build_box(path, name, version, branch, build_server):
    """
    Build a vagrant box.

    :param FilePath path: Directory containing ``Vagrantfile``.
    :param bytes name: Base name of vagrant box. Used to build filename.
    :param bytes version: Version of vagrant box. Used to build filename.
    :param bytes branch: Branch to get flocker RPMs from.
    :param build_server: Base URL of build server to download RPMs from.
    """
    box_path = path.child('%s%s%s.box'
                          % (name, '-' if version else '', version))
    json_path = path.child('%s.json' % (name,))

    # Destroy the box to begin, so that we are guaranteed
    # a clean build.
    run(['vagrant', 'destroy', '-f'], cwd=path.path)

    env = os.environ.copy()
    rpm_version, rpm_release = make_rpm_version(version)
    env.update({
        'FLOCKER_RPM_VERSION': '%s-%s' % (rpm_version, rpm_release),
        'FLOCKER_BRANCH': branch,
        'FLOCKER_BUILD_SERVER': build_server,
        })
    run(['vagrant', 'box', 'update'], cwd=path.path)
    run(['vagrant', 'up'], cwd=path.path, env=env)
    run(['vagrant', 'package', '--output', box_path.path], cwd=path.path)

    # And destroy at the end to save space.  If one of the above commands fail,
    # this will be skipped, so the image can still be debugged.
    run(['vagrant', 'destroy', '-f'], cwd=path.path)

    metadata = box_metadata(name, version, box_path)
    json_path.setContent(json.dumps(metadata))


def main(args, base_path, top_level):
    """
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the flocker repository.
    """
    options = BuildOptions(base_path=base_path, top_level=top_level)

    try:
        options.parseOptions(args)
    except usage.UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        sys.stderr.write(options.getUsage())
        raise SystemExit(1)

    sys.stdout.write("Building %s box from %s.\n"
                     % (options['box'], options['path']))
    build_box(
        path=options['path'],
        name='flocker-' + options['box'],
        version=options['flocker-version'],
        branch=options['branch'],
        build_server=options['build-server'],
        )
