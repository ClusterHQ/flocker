# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Era information for Flocker nodes.

Every time a node reboots it gets a new, globally unique era.
"""

import sys
from uuid import UUID

from zope.interface import implementer

from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from twisted.python.usage import Options
from twisted.python.runtime import platform

from ..common.script import (
    ICommandLineScript, flocker_standard_options, FlockerScriptRunner,
)


_BOOT_ID = FilePath(b"/proc/sys/kernel/random/boot_id")


def get_era():
    """
    :return UUID: A node- and boot-specific globally unique id.
    """
    return UUID(hex=_BOOT_ID.getContent().strip())


@flocker_standard_options
class EraOptions(Options):
    """
    Command line options for ``flocker-node-era``.
    """
    longdesc = (
        "Print the current node's era to stdout. The era is a unique"
        "identifier per reboot per node, and can be used to discover the"
        "current node's state safely using Flocker's REST API.\n"
    )

    synopsis = "Usage: flocker-node-era"


@implementer(ICommandLineScript)
class EraScript(object):
    """
    Output the era to stdout.
    """
    def main(self, reactor, options):
        if not platform.isLinux():
            raise SystemExit("flocker-node-era only works on Linux.")
        sys.stdout.write(str(get_era()))
        sys.stdout.flush()
        return succeed(None)


def era_main():
    """
    Entry point for ``flocker-node-era`` command-line tool.
    """
    return FlockerScriptRunner(
        script=EraScript(),
        options=EraOptions(),
        logging=False).main()
