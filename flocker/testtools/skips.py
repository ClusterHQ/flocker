# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Utilities to help with skipping tests.
"""

from unittest import SkipTest
from functools import wraps


def fail_if_skipped(test_item):
    """
    Check whether to fail the given test object if it will be skipped.

    :param test_object: test method or class with a skip decorator.

    :return: True if ``test_object`` is covered by environment variable
        FLOCKER_TEST_NO_SKIPS, else False.
    """
    return True

# The following functions need suitable names.
# Ideally those names would read well, like how
# skipUnless(SELENIUM_INSTALLED) reads like "skip unless selenium is
# installed".
# One option is to have them called skipIf and skipUnless, like the unittest
# methods, and then only import lines must be changed.
# another option is "skipOrFailUnless" and "skipOrFailIf"


def skipUnless2(condition, reason):
    """
    A test object decorator to skip the test unless ``condition`` evaluates to
    ``True``. Fail the test if an environment variable says to fail the
    decorated test if it is going to be skipped.

    See unittest.skipUnless for parameter documentation.
    """
    def fail_or_skip(test_item):
        if condition:
            return test_item
        elif fail_if_skipped(test_item=test_item):
            return lambda test_item: test_item.fail(reason)
        else:

            @wraps(test_item)
            def skip_wrapper(*args, **kwargs):
                raise SkipTest(reason)
            return skip_wrapper

    return fail_or_skip


def skipIf2(condition, reason):
    """
    A test object decorator to skip the test if ``condition`` evaluates to
    ``True``. Fail the test if an environment variable says to fail the
    decorated test if it is going to be skipped.

    See unittest.skipIf for parameter documentation.
    """

# also handle all raise SkipTests
# also handle .skip

# This requires follow-up issues to modify tox configurations and buildbot
# builders

# all skips will have to be changed
