# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for :module:`admin.merge_pr`.
"""

from datetime import datetime
import os
import subprocess

from hypothesis import given
from hypothesis.strategies import (
    booleans,
    dictionaries,
    fixed_dictionaries,
    integers,
    just,
    lists,
    one_of,
    sampled_from,
    text,
    )
from pyrsistent import pmap, plist

from flocker.testtools import TestCase

from admin import merge_pr


SCRIPT_FILENAME = 'merge-pr'
SCRIPT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           SCRIPT_FILENAME)


def run_script(args):
    return subprocess.check_output([SCRIPT_FILE] + args)


class SmokeTests(TestCase):
    """
    Basic tests of running the script.
    """

    def test_help(self):
        output = run_script(['--help'])
        self.assertIn("Merge a branch when all the tests pass.", output)


class URLTests(TestCase):
    """
    Test for URL manipulation.
    """

    def test_url_path(self):
        """
        Correct path from a full URL.
        """
        path = '/ClusterHQ/flocker/pull/1717'
        self.assertEqual(path, merge_pr.url_path('https://github.com' + path))

    def test_url_path_no_hostname(self):
        """
        Correct path from a URL path.
        """
        path = '/ClusterHQ/flocker/pull/1717'
        self.assertEqual(path, merge_pr.url_path(path))

    def test_url_path_parts(self):
        """
        Correct segments from a full URL.
        """
        path_parts = ['ClusterHQ', 'flocker', 'pull', '1717']
        self.assertEqual(
            [''] + path_parts,
            merge_pr.url_path_parts(
                'https://github.com/' + '/'.join(path_parts)))

    def test_url_path_parts_no_hostname(self):
        """
        Correct segments from a URL path.
        """
        path_parts = ['ClusterHQ', 'flocker', 'pull', '1717']
        self.assertEqual(
            [''] + path_parts,
            merge_pr.url_path_parts('/' + '/'.join(path_parts)))

    def test_pr_api_url(self):
        """
        Correct API URL for a full URL.
        """
        self.assertEqual(
            'https://api.github.com/repos/ClusterHQ/flocker/pulls/1717',
            merge_pr.pr_api_url_from_web_url(
                'https://github.com/ClusterHQ/flocker/pull/1717'))


# The max here corresponds to the latest date that datetime supports
datetimes = integers(
    min_value=0,
    max_value=253402300799
).map(datetime.utcfromtimestamp)
"""Strategy for generating `datetime` objects."""


def commit_statuses(**kwargs):
    """
    Create a strategy for GitHub commit status dicts.

    :param **kwargs: alter the strategy for a particular
        key of the status dict, e.g. state=just(u'success')
        will fix the state key of the dict to that string.
    :return strategy: a strategy.
    """
    base = {'updated_at': datetimes,
            'state': text(),
            'context': text(average_size=2),
            'target_url': text(average_size=2),
            }
    base.update(**kwargs)
    return fixed_dictionaries(base)


jenkins_results = sampled_from(merge_pr.JenkinsResults.iterconstants())
"""Strategy for generating JenkinsResults values."""


class StatusesTests(TestCase):
    """
    Tests for interpretation of commit statuses.

    https://developer.github.com/v3/repos/statuses/
    """

    @given(commit_statuses())
    def test_final_status_one(self, status):
        """
        Final status of one status is itself.
        """
        self.assertEqual(status, merge_pr.final_status([status]))

    @given(commit_statuses(), commit_statuses())
    def test_final_status_many(self, status1, status2):
        """
        Final status of a list is the latest.
        """
        target = status1
        if status2['updated_at'] > status1['updated_at']:
            target = status2
        self.assertEqual(target, merge_pr.final_status([status2, status1]))

    @given(commit_statuses(state=text().filter(lambda x: x != u'success')))
    def test_not_success(self, status):
        """
        Always `not_success` for anything except 'success'.
        """
        self.assertEqual(True, merge_pr.not_success(status))

    @given(commit_statuses(state=just(u'success')))
    def test_not_success_success(self, status):
        """
        `not_success` False for 'success'.
        """
        self.assertEqual(False, merge_pr.not_success(status))

    @given(commit_statuses(), jenkins_results)
    def test_format_status(self, status, jenkins):
        """
        `format_status` produces unicode that mentions the context and url.
        """
        formatted = merge_pr.format_status((status, jenkins))
        self.assertIsInstance(formatted, unicode)
        self.assertIn(status['context'], formatted)
        self.assertIn(status['target_url'], formatted)


# These strategies are far from complete coverage of the possible
# Jenkins API responses.

jenkins_builds = fixed_dictionaries(dict(
    result=sampled_from([None, 'FAILURE', 'ABORTED', 'SUCCESS'])))
"""Strategy for generating records of individual builds of a Jenkins job."""


NO_BUILDS = object()
"""
Sentinel to say that `jenkins_build_results` should not include the builds key.
"""


def jenkins_build_results(inQueue=None, builds=None):
    """Create a strategy for generating Jenkins API information for a job.

    :param strategy inQueue: strategy for the inQueue key, or None to use
        the default.
    :param strategy builds: strategy for populating the builds key, or None
        for the default. The special value `NO_BUILDS` will mean that the
        builds key is not in the resulting dict at all.
    :return strategy: a strategy.
    """
    strats = []
    if inQueue is None:
        inQueue = booleans()
        strats.append(just(pmap()))
    without_builds = fixed_dictionaries(dict(
        inQueue=inQueue))
    if builds is None or builds is NO_BUILDS:
        strats.append(without_builds)
    if builds is None:
        builds = lists(jenkins_builds, average_size=1)
    if builds is not NO_BUILDS:
        with_builds = fixed_dictionaries(dict(
            inQueue=inQueue,
            builds=builds,
            property=dictionaries(
                text(max_size=2), text(max_size=2),
                average_size=1, max_size=2)))
        strats.append(with_builds)
    return one_of(*strats)


class JenkinsResultsTests(TestCase):
    """
    Tests for interpretation of build results from Jenkins.
    """

    @given(jenkins_build_results())
    def test_result_types(self, info):
        """
        Result always a tuple (`JenkinsResults`, Maybe[dict])
        """
        result, params = merge_pr.jenkins_info_from_response(info)
        self.assertIn(result, list(merge_pr.JenkinsResults.iterconstants()))
        if params is not None:
            self.assertIsInstance(params, dict)

    @given(jenkins_build_results(inQueue=just(True)))
    def test_in_queue(self, info):
        """
        Job with inQueue = True is `RUNNING`.
        """
        result, params = merge_pr.jenkins_info_from_response(info)
        self.assertEqual(merge_pr.JenkinsResults.RUNNING, result)
        self.assertEqual({}, params)

    @given(jenkins_build_results(inQueue=just(False), builds=NO_BUILDS))
    def test_builds_not_present(self, info):
        """
        Job without a builds list is `UNKNOWN`.
        """
        result, params = merge_pr.jenkins_info_from_response(info)
        self.assertEqual(merge_pr.JenkinsResults.UNKNOWN, result)
        self.assertEqual({}, params)

    @given(jenkins_build_results(inQueue=just(False), builds=just(plist())))
    def test_no_builds(self, info):
        """
        Job with empty builds list is `NOTRUN`.
        """
        result, params = merge_pr.jenkins_info_from_response(info)
        self.assertEqual(merge_pr.JenkinsResults.NOTRUN, result)
        self.assertEqual({}, params)
