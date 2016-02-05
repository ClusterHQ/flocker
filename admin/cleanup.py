# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Utilities for cloud resource cleanup.
"""
import sys

from twisted.internet.defer import succeed
from twisted.python.usage import Options, UsageError


class CleanupCloudResourcesOptions(Options):
    """

    """


def cleanup_cloud_resources_main(reactor, args, base_path, top_level):
    options = CleanupCloudResourcesOptions()

    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write(
            "Usage Error: %s: %s\n" % (
                base_path.basename(), e
            )
        )
        raise SystemExit(1)
    return succeed(None)
