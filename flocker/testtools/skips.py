# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Utilities to help with skipping unit and functional tests.
"""

from unittest import skipUnless

def check_if_in_flocker_test_no_skips(test_object):
    return False
    # return True if test is covered by FLOCKER_TEST_NO_SKIPS, else False

def skipUnless2(condition, message):
    def maybe_ignore_skips(function):
        if check_if_in_flocker_test_no_skips(test_object=function):
            return function
        else:
            return skipUnless(condition, message)

    return maybe_ignore_skips
    # check the environment variable FLOCKER_TEST_NO_SKIPS
    # get modules defined in FLOCKER_TEST_NO_SKIPS
    # if decorated function is in one of those modules, return the function
    # without the skipUnless decorator
    # same for skipIf
    # should this be called skipUnless and so import lines only can be changed
    # alternatively it could have a unique function name e.g. skipUnlessForced
    # one issue with that is that:
    # skipUnless(SELENIUM_INSTALLED) reads like "skip unless selenium is installed"
    # skipUnlessForced(SELENIUM_INSTALLED) does not read as clearly

# also handle all raise SkipTests
# also handle .skip

# follow up issues for skipping setUp when skipping tests
# add to tox / buildbot reconfiguration
# check that this will work with tox
# document this in CONTRIBUTING.rst
