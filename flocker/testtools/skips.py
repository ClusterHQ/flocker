# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Utilities to help with skipping tests.
"""


def fail_if_skipped(test_item):
    """
    Check whether to fail the given test object if it will be skipped.

    :param test_object: test method or class with a skip decorator.

    :return: True if ``test_object`` is covered by environment variable
        FLOCKER_TEST_NO_SKIPS, else False.
    """
    return True


def skipUnless(condition, reason):
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
            return lambda test_item: test_item.skipTest(reason)

    return fail_or_skip


def skipIf(condition, reason):
    """
    A test object decorator to skip the test if ``condition`` evaluates to
    ``True``. Fail the test if an environment variable says to fail the
    decorated test if it is going to be skipped.

    See unittest.skipIf for parameter documentation.
    """
    def fail_or_skip(test_item):
        if not condition:
            return test_item
        elif fail_if_skipped(test_item=test_item):
            return lambda test_item: test_item.fail(reason)
        else:
            return lambda test_item: test_item.skipTest(reason)

    return fail_or_skip

class SkipTest(Exception):
    """
    Similar to ``unittest.skipTest`` except the test being run when this is
    raised will fail if an environment variable says to fail the
    decorated test if it is going to be skipped.
    """
    def __init__(self, test_item, value):
        self.value = value
        if fail_if_skipped(test_item=test_item):
            test_item.fail(value)
        else:
            test_item.skipTest(value)

    def __str__(self):
        return repr(self.value)
