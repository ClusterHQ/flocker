# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Logic for handling flaky tests.
"""


def flaky(jira_key):
    """
    Mark a test as flaky.

    A 'flaky' test is one that sometimes passes but sometimes fails. Marking a
    test as flaky means both failures and successes are expected, and that
    neither will fail the test run.

    :param unicode jira_key: The JIRA key of the bug for this flaky test,
        e.g. 'FLOC-2345'
    :return: A decorator that can be applied to `TestCase` methods.
    """
    # XXX: This raises a crappy error message if you forgot to provide a JIRA
    # key. Is there a way to provide a good one?

    # TODO (see FLOC-3281):
    # - allow specifying which exceptions are expected
    # - retry on expected exceptions
    #   - parametrize on retry options
    # - provide interesting & parseable logs for flaky tests

    def wrapper(test_method):
        return test_method
    return wrapper
