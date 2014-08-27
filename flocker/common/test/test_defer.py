# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.common._defer``.
"""

import gc

from .._defer import gather_deferreds

from twisted.internet.defer import fail, FirstError, succeed, Deferred
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase


class GatherDeferredsTests(TestCase):
    """
    Tests for ``gather_deferreds``.
    """
    def test_logging(self):
        """
        Failures in the supplied ``deferreds`` are all logged.
        """
        expected_failure1 = Failure(ZeroDivisionError('test_logging1'))
        expected_failure2 = Failure(ZeroDivisionError('test_logging2'))

        self.failureResultOf(
            gather_deferreds(
                [fail(expected_failure1), fail(expected_failure2)]
            )
        )

        self.assertEqual(
            [expected_failure1, expected_failure2],
            self.flushLoggedErrors(ZeroDivisionError)
        )

    def test_errors_logged_immediately(self):
        """
        Failures in the supplied ``deferreds`` are logged immediately.
        """
        d1 = Deferred()
        d2 = Deferred()
        gathering = gather_deferreds([d1, d2])

        # The deferred fires with an error
        expected_error = ZeroDivisionError()
        d1.errback(expected_error)

        # d2 has not yet fired, but the error is logged immediately
        logged_errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertEqual([expected_error], [f.value for f in logged_errors])

        d2.callback(None)
        self.failureResultOf(gathering)

    def test_success(self):
        """
        The successful results of the supplied ``deferreds`` are returned.
        """
        expected_result1 = object()
        expected_result2 = object()

        d = gather_deferreds(
            [succeed(expected_result1), succeed(expected_result2)])

        results = self.successResultOf(d)
        self.assertEqual([expected_result1, expected_result2], results)

    def test_first_error(self):
        """
        If any of the supplied ``deferreds`` fail, ``gather_deferreds`` will
        errback with a ``FirstError``.
        """
        d = gather_deferreds(
            [succeed('SUCCESS1'),
             fail(ZeroDivisionError('failure1')),
             succeed('SUCCESS2')])

        self.failureResultOf(d, FirstError)

        self.flushLoggedErrors(ZeroDivisionError)

    def test_first_error_value(self):
        """
        The ``FirstError`` has a reference to the ``Failure`` produced by the
        first of the supplied ``deferreds`` that failed.
        """
        failure1 = Failure(ZeroDivisionError('failure1'))
        failure2 = Failure(ZeroDivisionError('failure1'))

        d = gather_deferreds([fail(failure1), succeed(None), fail(failure2)])

        first_error = self.failureResultOf(d, FirstError)
        self.assertIs(first_error.value.subFailure, failure1)

        self.flushLoggedErrors(ZeroDivisionError)

    def test_fire_when_all_fired(self):
        """
        The ``Deferred`` returned by ``gather_deferreds`` does not fire until
        all the supplied ``deferreds`` have either erred back or called back.
        """
        d1 = Deferred()
        d2 = Deferred()
        d3 = Deferred()
        gathering = gather_deferreds([d1, d2, d3])

        # The second deferred fires first, with an error
        d2.errback(ZeroDivisionError('test_consume_errors1'))

        # But the gathered list does not fire...
        self.assertNoResult(gathering)

        # The remaining deferreds then callback...
        d1.callback(None)
        d3.callback(None)

        # ...and the gathered list has now fired.
        self.failureResultOf(gathering)

        self.flushLoggedErrors(ZeroDivisionError)

    def test_consume_errors(self):
        """
        Errors in the supplied ``deferreds`` are always consumed so that they
        are not logged during garbage collection.
        """
        # Keep references to the deferreds so that we can trigger garbage
        # collection later in the test.
        d1 = fail(ZeroDivisionError())
        d2 = succeed(None)
        d3 = fail(ZeroDivisionError())

        self.failureResultOf(gather_deferreds([d1, d2, d3]))

        # Flush the errors which will have been logged immediately
        self.flushLoggedErrors(ZeroDivisionError)

        # When the original deferreds are garbage collected, there is no
        # further logging of errors.
        del d1, d2, d3
        gc.collect()
        self.assertEqual([], self.flushLoggedErrors(ZeroDivisionError))
