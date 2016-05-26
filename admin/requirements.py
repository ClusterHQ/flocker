# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Utilities for generating requirements files.
"""

import sys
from contextlib import contextmanager
import os
import shutil
from subprocess import check_call
from tempfile import NamedTemporaryFile, mkdtemp

from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath

MANYLINUX_IMAGE = "quay.io/pypa/manylinux1_x86_64:latest"
REQUIREMENTS_IMAGE = "clusterhq/flocker_update_requirements"


@contextmanager
def temporary_directory(suffix):
    temporary_directory = FilePath(mkdtemp(suffix=suffix))
    try:
        yield temporary_directory
    finally:
        temporary_directory.remove()


def requirements_from_infile(infile):
    outfile = infile.sibling(infile.basename()[:-len(".in")])
    with NamedTemporaryFile(
        prefix="{}.".format(outfile.basename()),
        suffix=".created-by-update-requirements-entrypoint",
        dir=os.path.dirname(outfile.parent().path),
        delete=False,
    ) as temporary_outfile:
        print "PROCESSING", infile
        check_call(
            ["docker", "run",
             "--rm",
             "--volume", "{}:/requirements.txt".format(infile.path),
             REQUIREMENTS_IMAGE],
            stdout=temporary_outfile
        )
        shutil.copymode(outfile.path, temporary_outfile.name)
        os.rename(temporary_outfile.name, outfile.path)


class UpdateRequirementsOptions(Options):
    """
    Command line options for ``update-requirements``.
    """
    optFlags = [
        ["no-build", False,
         "Do not rebuild the requirements Docker image."]
    ]


def build_requirements_image(image_tag, dockerfile, requirements_directory):
    check_call(
        ["docker", "pull", MANYLINUX_IMAGE]
    )

    with temporary_directory(
            suffix=".update-requirements.build_requirements_image"
    ) as docker_build_directory:
        dockerfile.copyTo(
            docker_build_directory.child('Dockerfile')
        )
        dockerfile.sibling("update-requirements-entrypoint").copyTo(
            docker_build_directory.child('entrypoint')
        )

        requirements_directory.copyTo(
            docker_build_directory.child('requirements')
        )
        check_call(
            ["docker", "build",
             "--tag", image_tag,
             docker_build_directory.path]
        )


def update_requirements_main(args, base_path, top_level):
    """
    The main entry point for ``update-requirements``.
    """
    options = UpdateRequirementsOptions()

    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write(
            u"{}\n"
            u"Usage Error: {}: {}\n".format(
                unicode(options), base_path.basename(), e
            ).encode('utf-8')
        )
        raise SystemExit(1)

    requirements_directory = top_level.child('requirements')

    dockerfile = top_level.descendant(["admin", "requirements.Dockerfile"])

    if not options["no-build"]:
        build_requirements_image(
            REQUIREMENTS_IMAGE,
            dockerfile,
            requirements_directory
        )

    for infile in requirements_directory.globChildren("*.in"):
        requirements_from_infile(infile)
