# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Find and report on tests marked as flaky.
"""

import sys

from testtools import clone_test_with_new_id, iterate_tests
from twisted.python.usage import Options, UsageError
from twisted.trial.reporter import TreeReporter
from twisted.trial.runner import TestLoader

from flocker.testtools._flaky import _get_flaky_annotation


def _load_tests(name):
    """
    Find all the tests under ``name``.

    :param str name: The fully-qualified Python name of an object.
    :return: A ``TestSuite`` or ``TestCase`` containing all the tests.
    """
    loader = TestLoader()
    return loader.loadByName(name, recurse=True)


def _iter_tests(names):
    """
    Given a list of names, iterate through all the tests in them.
    """
    for name in names:
        suite = _load_tests(name)
        for test in iterate_tests(suite):
            yield test


def get_flaky_annotation(case):
    """
    Given a test, return the flaky annotation object.

    If the test failed to load somehow (i.e. was an ``ErrorHolder``),
    re-raise the reason it failed to load.
    """
    error = getattr(case, 'error', None)
    if error:
        raise error[0], error[1], error[2]
    return _get_flaky_annotation(case)


def find_flaky_tests(suites):
    """
    Find all flaky tests in the given suites.
    """
    for test in _iter_tests(suites):
        annotation = get_flaky_annotation(test)
        if annotation:
            yield test, annotation


def report_flaky_tests(output, flaky_tests):
    """
    Report on flaky tests.
    """
    for test in flaky_tests:
        output.write('{}\n'.format(test))


def report_issues(output, flaky_tests):
    """
    Print all issues for flaky tests.
    """
    jira_keys = frozenset().union(
        *(flaky.jira_keys for (_, flaky) in flaky_tests))
    for jira_key in sorted(jira_keys):
        output.write('{}\n'.format(jira_key))


def report_tests(output, flaky_tests):
    """
    Print all flaky tests.
    """
    tests = list(test.id() for (test, _) in flaky_tests)
    for test in sorted(tests):
        output.write('{}\n'.format(test))


def report_test_tree(output, flaky_tests):
    """
    Print all flaky tests as a tree.
    """
    reporter = TreeReporter(output)
    for (test, flaky) in flaky_tests:
        new_test = clone_test_with_new_id(test, '{}({})'.format(test.id(), ', '.join(flaky.jira_keys)))
        reporter.startTest(new_test)
        reporter.addSuccess(new_test)
        reporter.stopTest(new_test)
    reporter.done()


_REPORTS = {
    'issues': report_issues,
    'tests': report_tests,
    'tree': report_test_tree,
}
"""
All of the reports we offer. Keys will be valid arguments to --report.
"""


def _to_report(name):
    """
    Ensure that ``name`` is a valid report.
    """
    if name in _REPORTS:
        return name
    raise UsageError(
        "Unrecognized report {}. {}".format(name, _to_report.coerceDoc))
_to_report.coerceDoc = "Must be one of: {}".format(', '.join(_REPORTS.keys()))


class FindFlakyTestsOptions(Options):
    """
    Options for finding flaky tests.
    """

    optParameters = [
        ['report', 'r', 'tree', 'The report to use', _to_report]
    ]

    def __init__(self, name, *args, **kwargs):
        super(FindFlakyTestsOptions, self).__init__(*args, **kwargs)
        self._name = name
        self.synopsis = "{} [options] [TEST...]".format(name)

    def parseArgs(self, *suites):
        """
        Accept an arbitrary number of suites, specified as fully-qualified
        Python names.
        """
        if not suites:
            raise UsageError('Must provide name of at least one test suite')
        self['suites'] = suites


def find_flaky_tests_main(args, base_path, top_level, stdout=None,
                          stderr=None):
    """
    Find and report on tests marked as flaky.
    """
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    # XXX: Boilerplate copied from release.py, very similar (but not similar
    # enough!) to boilerplate in flocker.common.script.
    options = FindFlakyTestsOptions(base_path.basename())
    try:
        options.parseOptions(args)
    except UsageError as e:
        stdout.write(str(options))
        stdout.write("\n")
        stderr.write("{}: {}\n".format(base_path.basename(), e))
        sys.exit(1)

    flaky_tests = find_flaky_tests(options['suites'])
    _REPORTS[options['report']](stdout, flaky_tests)
