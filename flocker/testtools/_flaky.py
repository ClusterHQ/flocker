# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Logic for handling flaky tests.

XXX: Not all of this code actually belongs here, but while writing it's
convenient to have one place to put everything.
"""


def flaky(test_method):
    """
    Mark a test as flaky.

    A 'flaky' test is one that sometimes passes but sometimes fails. Marking a
    test as flaky means both failures and successes are expected, and that
    neither will fail the test run.

    :param function test_method: The test method to mark as flaky.
    :return: A decorated version of ``test_method``.
    """
    # TODO
    # - allow specifying which exceptions are expected
    # - retry on expected exceptions
    #   - parametrize on retry options
    #     - perhaps `loop_until` should take a generator of sleep intervals,
    #       so we can use same routine for backoff
    # - provide interesting & parseable logs for flaky tests
    return test_method
