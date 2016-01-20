# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Find and report on tests marked as flaky.
"""

import sys
from twisted.python.usage import Options, UsageError


class FindFlakyTestsOptions(Options):
    """
    Options for finding flaky tests.
    """

    def parseArgs(self, *suites):
        """
        Accept an arbitrary number of suites, specified as fully-qualified
        Python names.
        """
        self['suites'] = suites


def find_flaky_tests(suites):
    """
    Find all flaky tests in the given suites.
    """
    return []


def report_flaky_tests(output, flaky_tests):
    """
    Report on flaky tests.
    """
    for test in flaky_tests:
        output.write('{}\n'.format(test))


def find_flaky_tests_main(args, base_path, top_level, stdout=None,
                          stderr=None):
    """
    Find and report on tests marked as flaky.
    """
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    # XXX: Boilerplate copied from release.py, very similar (but not similar
    # enough!) to boilerplate in flocker.common.script.
    options = FindFlakyTestsOptions()
    try:
        options.parseOptions(args)
    except UsageError as e:
        stderr.write("{}: {}\n".format(base_path.basename(), e))
        sys.exit(1)

    flaky_tests = find_flaky_tests(options['suites'])
    report_flaky_tests(stdout, flaky_tests)
