# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Utilities to help with skipping tests.
"""

from unittest import skipIf, skipUnless

def ignore_skip(test_object):
    """
    Check whether to ignore any skip decorators on a test object.

    :param test_object: test method or class with a skip decorator.

    :return: True if ``test_object`` is covered by environment variable
        FLOCKER_TEST_NO_SKIPS, else False.
    """

# The following functions need suitable names.
# Ideally those names would read well, like how:
# skipUnless(SELENIUM_INSTALLED) reads like "skip unless selenium is installed".
# One option is to have them called skipIf and skipUnless, like the unittest
# methods, and then only import lines must be changed.

def skipUnlessForcedOr(condition, reason):
    """
    Ignore skipUnless if an environment variable has been set instructing to do
    so.

    See unittest.skipUnless for parameter documentation.
    """
    def skip_unless_condition_or_forced(function):
        if ignore_skip(test_object=function):
            return function
        else:
            return skipUnless(condition, reason)

    return skip_unless_condition_or_forced

def skipUnlessForcedIf(condition, reason):
    """
    Ignore skipIf if an environment variable has been set instructing to do
    so.

    See unittest.skipIf for parameter documentation.
    """
    def skip_if_condition_or_forced(function):
        if ignore_skip(test_object=function):
            return function
        else:
            return skipIf(condition, reason)

    return skip_if_condition_or_forced

# also handle all raise SkipTests
# also handle .skip

# follow up issues for skipping setUp when skipping tests
# add to tox / buildbot reconfiguration
# check that this will work with tox
# document this in CONTRIBUTING.rst
# tests for this
