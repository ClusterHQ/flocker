# -*- test-case-name: flocker.common.test.test_logging -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Simple logging utilities for flocker.
"""

from inspect import getmodule, stack

from eliot import Message


_ERROR_TOKEN = u'ERROR'


def _compute_message_type(frame_tuple):
    """
    Constructs a human readable message type from a frame of a traceback.

    The resulting string should have the module name, function name, and line
    number encoded so that it is trivial to figure out where the log came from.

    Format of output:

    <module>:<function name>:<line number>

    :param frame_tuple: The stack frame tuple to turn into a message type.
        Should normally be one stack level higher than the function that calls
        this. (i.e. ``inspect.stack()[1]`` )

    :returns unicode: The human readable message_type for a log originating at
        the given stack frame.
    """
    frame, _, line, func, _, _ = frame_tuple
    return u':'.join([getmodule(frame).__name__, func, unicode(line)])


def log_info(**kwargs):
    """
    Simple logging wrapper around Eliot messages.

    This fills in the message type and passes all other arguments on to
    ``Message.log``.
    """
    Message.log(
        message_type=_compute_message_type(stack()[1]),
        **kwargs
    )


def log_error(**kwargs):
    """
    Simple logging wrapper around Eliot messages that should cause acceptance
    tests to fail.

    This fills in the message type, adds a token to indicate it is an error,
    and passes all other arguments on to ``Message.log``.
    """
    Message.log(
        message_type=_compute_message_type(stack()[1]),
        level=_ERROR_TOKEN,
        **kwargs
    )


def is_error(message):
    """
    Determines if the passed in Eliot message was an error message.

    :param dict message: The Eliot message to examine.

    :returns bool: If the passed in message is an error that should fail the
        acceptance tests.
    """
    return message.get('level') == _ERROR_TOKEN
