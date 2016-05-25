# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Utilities for generating requirements files.
"""
import sys

from twisted.python.usage import Options, UsageError


class UpdateRequirementsOptions(Options):
    """
    Command line options for ``update-requirements``.
    """


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
