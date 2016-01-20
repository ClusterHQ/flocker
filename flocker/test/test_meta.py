# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the test running process.
"""

from unittest import skipUnless, TestSuite
from pprint import pformat

from yaml import safe_load

from pyrsistent import pset

from twisted.python.filepath import FilePath
from twisted.trial.runner import TestLoader

from flocker.testtools import TestCase


REPOSITORY = FilePath(__file__).parent().parent().parent()


def get_tests_for(python_name):
    """
    Find all tests for the given ``python_name``.

    :param python_name: Either directory in ``REPOSITORY`` or a Python FQPN
        importable from ``REPOSITORY``.
    :return: PSet of test names.
    """
    def _extract_ids(t):
        if isinstance(t, TestSuite):
            result = pset()
            for sub_tests in t:
                result = result | _extract_ids(sub_tests)
            return result
        else:
            return pset([t.id()])

    loader = TestLoader()
    tests = loader.loadByName(python_name, recurse=True)
    return _extract_ids(tests)


class EnsureAllTestsRun(TestCase):
    """
    Safety net tests: make sure our Jenkins config is running all tests.

    There is an obvious problem that if ``flocker.test`` tests aren't
    being run then this won't be caught!
    """
    @skipUnless(b".git" in REPOSITORY.listdir(),
                "Need to run out of git checkout.")
    def test_build_yaml_includes_all_repository_tests(self):
        """
        Ensure that the split-up test structure of ``build.yaml`` covers all
        code in the Flocker repository.

        This only makes sense when running out of a git checkout.

        Caveats:
        * This has no idea whether tests are actually being run in an
          appropriate environment. E.g. maybe we're only running tests
          that require root in non-root environment, and so they are
          always skipped.
        * Acceptance tests are run using different mechanism that
          isn't well covered by this check.
        """
        build_config = safe_load(REPOSITORY.child(b"build.yaml").getContent())
        configured_tests = pset()

        for jobs in build_config[u"job_type"].values():
            for job in jobs.values():
                for module in job.get(u"with_modules", []):
                    configured_tests = configured_tests | get_tests_for(module)

        expected_tests = pset()
        for child in REPOSITORY.children():
            if child.isdir() and b"__init__.py" in child.listdir():
                expected_tests = expected_tests | get_tests_for(
                    child.basename())

        # This test may fail erroneously if you have .pyc files lying
        # around with extra tests from no-longer existent modules. So
        # delete those. Also it implicitly assumes test run environment is
        # the same as the checkout in terms of what tests it has.
        self.assertTrue(
            configured_tests == expected_tests,
            ("Tests that are unexpected but in build.yaml: {}\n\n"
             "Tests that are missing from build.yaml: {}\n\n").format(
                 pformat(list(configured_tests - expected_tests)),
                 pformat(list(expected_tests - configured_tests))))
