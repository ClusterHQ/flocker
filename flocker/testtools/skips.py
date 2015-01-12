# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Utilities to help with skipping unit and functional tests.
"""

from unittest import skipUnless

def 
def skipUnless2(condition, message):
    # check the environment variable FLOCKER_TEST_NO_SKIPS
    # get modules defined in FLOCKER_TEST_NO_SKIPS
    # if decorated function is in one of those modules, return the function
    # without the skipUnless decorator
    # same for skipIf