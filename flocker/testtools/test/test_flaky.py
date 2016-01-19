# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.testtools._flaky``.
"""

from itertools import repeat
from pprint import pformat
import unittest

from hypothesis import given
from hypothesis.strategies import (
    integers,
    lists,
    permutations,
    streaming,
    text,
)
import testtools
from testtools.matchers import (
    Contains,
    Equals,
    HasLength,
    MatchesAll,
    MatchesListwise,
)
from testtools.testresult.doubles import ExtendedTestResult

from .._flaky import (
    _FLAKY_ATTRIBUTE,
    _get_flaky_annotation,
    flaky,
    retry_flaky,
)
from .._testhelpers import (
    base_test_cases,
    has_results,
    only_skips,
    run_test,
    throw,
)


# A JIRA key is just some text.
jira_keys = text(average_size=5)

# Don't really want to run anything more than 5 times.
num_runs = integers(min_value=1, max_value=5)


class FlakyTests(testtools.TestCase):
    """
    Tests for ``@flaky`` decorator.
    """

    @given(integers())
    def test_decorated_function_executed(self, x):
        """
        ``@flaky`` decorates the given function sanely.
        """
        values = []

        @flaky(u'FLOC-XXXX')
        def f(x):
            values.append(x)
            return x

        y = f(x)
        self.expectThat(y, Equals(x))
        self.assertThat(values, Equals([x]))

    def _get_annotation_dict(self, f):
        """
        Get the flaky annotation dictionary for flaky function ``f``.
        """
        return getattr(f, _FLAKY_ATTRIBUTE).to_dict()

    @given(jira_keys, num_runs, num_runs)
    def test_annotation_dictionary(self, jira_key, max_runs, min_passes):
        [min_passes, max_runs] = sorted([min_passes, max_runs])

        @flaky(jira_key, max_runs, min_passes)
        def f(x):
            pass

        self.assertThat(self._get_annotation_dict(f), Equals({
            'min_passes': min_passes,
            'max_runs': max_runs,
            'jira_keys': set([jira_key]),
        }))

    @given(lists(jira_keys, min_size=1, average_size=2), num_runs, num_runs)
    def test_annotation_dictionary_multiple_keys(self, jira_keys, max_runs,
                                                 min_passes):
        [min_passes, max_runs] = sorted([min_passes, max_runs])

        @flaky(jira_keys, max_runs, min_passes)
        def f(x):
            pass

        self.assertThat(self._get_annotation_dict(f), Equals({
            'min_passes': min_passes,
            'max_runs': max_runs,
            'jira_keys': set(jira_keys),
        }))

    @given(lists(jira_keys, min_size=1, average_size=2), num_runs, num_runs,
           lists(jira_keys, min_size=1, average_size=2), num_runs, num_runs)
    def test_multiple_decorators(self, jira_keys1, max_runs1, min_passes1,
                                 jira_keys2, max_runs2, min_passes2):
        [min_passes1, max_runs1] = sorted([min_passes1, max_runs1])
        [min_passes2, max_runs2] = sorted([min_passes2, max_runs2])

        @flaky(jira_keys1, max_runs1, min_passes1)
        @flaky(jira_keys2, max_runs2, min_passes2)
        def f(x):
            pass

        self.assertThat(self._get_annotation_dict(f), Equals({
            'min_passes': max(min_passes1, min_passes2),
            'max_runs': max(max_runs1, max_runs2),
            'jira_keys': set(jira_keys1) | set(jira_keys2),
        }))

    def test_successful_flaky_test(self):
        """
        A successful flaky test is considered successful.
        """

        # We use 'testtools' here to avoid accidentally depending on Twisted
        # TestCase features, thus increasing complexity.
        class SomeTest(testtools.TestCase):

            run_tests_with = retry_flaky()

            @flaky(u'FLOC-XXXX')
            def test_something(self):
                pass

        test = SomeTest('test_something')
        self.assertThat(run_test(test), has_results(tests_run=Equals(1)))

    @given(jira_keys, num_runs, num_runs)
    def test_always_erroring_flaky_test(self, jira_keys, max_runs, min_passes):
        """
        A flaky test always errors out is recorded as erroring.
        """
        [min_passes, max_runs] = sorted([min_passes, max_runs])

        executions = repeat(lambda: throw(ValueError('failure')))

        class SomeTest(testtools.TestCase):

            run_tests_with = retry_flaky()

            @flaky(jira_keys, max_runs=max_runs, min_passes=min_passes)
            def test_something(self):
                next(executions)()

        test = SomeTest('test_something')
        result = run_test(test)
        self.expectThat(
            result, has_results(
                errors=HasLength(1),
                tests_run=Equals(1),
            )
        )
        [(found_test, exception)] = result.errors
        flaky_data = _get_flaky_annotation(test).to_dict()
        flaky_data.update({'runs': max_runs - min_passes + 1, 'passes': 0})
        self.assertThat(
            exception, MatchesAll(
                Contains('ValueError'),
                Contains(pformat(flaky_data)),
            )
        )

    @given(permutations([
        lambda: throw(ValueError('failure')),
        lambda: None,
        lambda: throw(RuntimeError('failure #2')),
    ]))
    def test_intermittent_flaky_test(self, test_methods):
        """
        A @flaky test that fails sometimes and succeeds other times counts as a
        pass, as long as it passes more than the given min_passes threshold.
        """
        # XXX: We could create an "exceptions" strategy.
        executions = iter(test_methods)

        class SomeTest(testtools.TestCase):

            run_tests_with = retry_flaky()

            @flaky(u'FLOC-XXXX', max_runs=len(test_methods), min_passes=1)
            def test_something(self):
                next(executions)()

        test = SomeTest('test_something')
        self.assertThat(run_test(test), has_results(tests_run=Equals(1)))

    @given(permutations([
        lambda: throw(ValueError('failure')),
        lambda: None,
        lambda: throw(RuntimeError('failure #2')),
    ]))
    def test_intermittent_flaky_test_that_errors(self, test_methods):
        """
        Tests marked with 'flaky' are retried if they fail, and marked as
        erroring / failing if they don't reach the minimum number of successes.
        """
        executions = iter(test_methods)

        class SomeTest(testtools.TestCase):
            run_tests_with = retry_flaky()

            @flaky(u'FLOC-XXXX', max_runs=len(test_methods), min_passes=2)
            def test_something(self):
                next(executions)()

        test = SomeTest('test_something')
        self.assertThat(run_test(test), has_results(
            tests_run=Equals(1),
            errors=HasLength(1),
        ))

    @given(permutations([
        lambda: throw(ValueError('failure')),
        lambda: None,
        lambda: throw(RuntimeError('failure #2')),
    ]))
    def test_intermittent_flaky_subclass(self, test_methods):
        """
        We sometimes subclass test classes in order to test different
        implementations of the same interface. A test within such a subclass
        can be marked as flaky, causing it to retry.
        """
        executions = iter(test_methods)

        class SomeTest(testtools.TestCase):
            run_tests_with = retry_flaky()

            def test_something(self):
                next(executions)()

        class SubclassTest(SomeTest):

            @flaky(u'FLOC-XXXX', max_runs=len(test_methods), min_passes=1)
            def test_something(self):
                super(SubclassTest, self).test_something()

        test = SubclassTest('test_something')
        self.assertThat(run_test(test), has_results(tests_run=Equals(1)))

    @given(jira_keys, num_runs, num_runs,
           streaming(text(average_size=10)).map(iter))
    def test_flaky_testtools_skipped_test(self, jira_keys, max_runs,
                                          min_passes, reasons):
        """
        If a test is skipped and also marked @flaky, we report it as skipped.
        """
        [min_passes, max_runs] = sorted([min_passes, max_runs])
        observed_reasons = []

        class SkippingTest(testtools.TestCase):
            run_tests_with = retry_flaky()

            @flaky(jira_keys, max_runs, min_passes)
            def test_skip(self):
                observed_reasons.append(reasons.next())
                self.skip(observed_reasons[-1])

        test = SkippingTest('test_skip')
        self.assertThat(run_test(test), only_skips(1, observed_reasons))

    @given(jira_keys)
    def test_sends_start_on_start(self, jira_keys):
        """
        Flaky tests send ``startTest`` as soon as they start.

        This means that we see the name of the test in the trial reporter
        (FLOC-3511) and that the recorded duration of the test is more-or-less
        accurate (FLOC-3499)
        """
        log = []

        class FlakyTest(testtools.TestCase):
            run_tests_with = retry_flaky()

            @flaky(jira_keys, 1, 1)
            def test_delayed(self):
                # Get a copy of the event log at this point of the test.
                self.log = list(log)

        test = FlakyTest('test_delayed')
        result = ExtendedTestResult(log)
        test.run(result)
        self.assertThat(test.log, Equals([('startTest', test)]))


class FlakyIntegrationTests(testtools.TestCase):
    """
    Tests that @flaky and retry_flaky interact well with our standard base
    test cases.
    """

    @given(base_test_cases, jira_keys, num_runs, num_runs,
           streaming(text(average_size=10)).map(iter))
    def test_flaky_skipped_test(self, base_test_case, jira_keys, max_runs,
                                min_passes, reasons):
        """
        If a test is skipped and also marked @flaky, we report it as skipped.

        Ensures that our workarounds for testing-cabal/unittest-ext#60
        work with @flaky support.
        """
        [min_passes, max_runs] = sorted([min_passes, max_runs])
        observed_reasons = []

        class SkippingTest(base_test_case):
            run_tests_with = retry_flaky()

            @flaky(jira_keys, max_runs, min_passes)
            def test_skip(self):
                observed_reasons.append(reasons.next())
                raise unittest.SkipTest(observed_reasons[-1])

        test = SkippingTest('test_skip')
        self.assertThat(run_test(test), only_skips(1, observed_reasons))

    @given(base_test_cases, jira_keys, num_runs, num_runs)
    def test_retry_by_default(self, base_test_case, jira_keys, max_runs,
                              min_passes):
        """
        Tests that inherit from our base test cases and use @flaky are retried
        by default.
        """
        [min_passes, max_runs] = sorted([min_passes, max_runs])

        class ErroringTest(base_test_case):
            @flaky(jira_keys, max_runs, min_passes)
            def test_error(self):
                1 / 0

        test = ErroringTest('test_error')

        # We expect the result of the run to be that one test was run and that
        # it produced an error that includes a traceback with the strings
        # "flaky:" (which comes from the flaky decorator, proving its effect)
        # and "ZeroDivisionError" which describes the exception the test
        # actually fails with.  Something like:
        #
        #  [(test, "error report including the two strings")]
        self.assertThat(
            run_test(test),
            has_results(
                tests_run=Equals(1),
                errors=MatchesListwise([
                    MatchesListwise([
                        Equals(test),
                        MatchesAll(
                            Contains('flaky:'),
                            Contains('ZeroDivisionError'),
                        ),
                    ])
                ]),
            ),
        )
