# -*- test-case-name: flocker.common.test.test_logging -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common.logging``
"""

from eliot.testing import capture_logging
from ...testtools import TestCase
from testtools.matchers import (
    AfterPreprocessing,
    AnyMatch,
    ContainsAll,
    Equals,
    MatchesAll,
    MatchesSetwise,
)
from inspect import currentframe, getframeinfo

from ..logging import log_info, log_error, is_error


def _dict_values_match(*args, **kwargs):
    """
    Matcher that matches a dict where each of they keys match the matcher
    passed in. Similar to ``MatchesStructure``, but for dictionaries rather
    than python objects.
    """
    matchers = dict(*args, **kwargs)

    def extract_val(key):

        def extract_val_for_key(d):
            return d.get(key)
        return extract_val_for_key
    return MatchesAll(*list(AfterPreprocessing(extract_val(key), value)
                            for key, value in matchers.iteritems()))


class LoggingTests(TestCase):
    """
    Tests for ``flocker.common.logging``.
    """

    @capture_logging(None)
    def test_log_info(self, logger):
        """
        ``log_info`` encodes module, function, and line number in the
        message_type, and passes other keyword arguments onto the message
        structure.
        """
        frame = getframeinfo(currentframe())
        log_info(key='VAL')
        line_no = frame.lineno + 1

        self.assertThat(
            logger.messages,
            AnyMatch(
                _dict_values_match(
                    message_type=ContainsAll(
                        [__name__, u'test_log_info', unicode(line_no)]),
                    key=Equals('VAL')
                )
            )
        )

    @capture_logging(None)
    def test_log_error(self, logger):
        """
        ``log_error`` encodes module, function, and line number in the
        message_type, and passes other keyword arguments onto the message
        structure.
        """
        frame = getframeinfo(currentframe())
        log_error(key='VAL')
        line_no = frame.lineno + 1

        self.assertThat(
            logger.messages,
            AnyMatch(
                _dict_values_match(
                    message_type=ContainsAll(
                        [__name__, u'test_log_error', unicode(line_no)]),
                    key=Equals('VAL')
                )
            )
        )

    @capture_logging(None)
    def test_errors_identifiable(self, logger):
        """
        Errors can be identified by ``is_error``.
        """
        log_info(info='message')
        log_error(error='message')
        self.assertThat(
            logger.messages,
            MatchesSetwise(
                MatchesAll(
                    _dict_values_match(
                        info=Equals('message')
                    ),
                    AfterPreprocessing(is_error, Equals(False)),
                ),
                MatchesAll(
                    _dict_values_match(
                        error=Equals('message')
                    ),
                    AfterPreprocessing(is_error, Equals(True)),
                )
            )
        )
