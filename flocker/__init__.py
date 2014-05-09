# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.test -*-

"""
Flocker is a hypervisor that provides ZFS-based replication and fail-over
functionality to a Linux-based user-space operating system.
"""

import sys
import os


def _logEliotMessage(data):
    """
    Route a serialized Eliot log message to the Twisted log.

    :param data: ``bytes``, a serialized message.
    """
    from twisted.python.log import msg
    from json import loads
    msg("ELIOT: " + data)
    if "eliot:traceback" in data:
        # Don't bother decoding every single log message...
        decoded = loads(data)
        if decoded.get(u"message_type") == u"eliot:traceback":
            msg("ELIOT Extracted Traceback:\n" + decoded["traceback"])



# Ugly but convenient. There should be some better way to do this...
# See https://twistedmatrix.com/trac/ticket/6939
if sys.argv and os.path.basename(sys.argv[0]) == 'trial':
    from eliot import addDestination
    addDestination(_logEliotMessage)
    del addDestination
