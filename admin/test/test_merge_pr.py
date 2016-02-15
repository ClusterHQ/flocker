# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for :module:`admin.merge_pr`.
"""

from datetime import datetime
import os
import subprocess

from hypothesis import assume, given
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
from pyrsistent import pmap

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
datetimes = integers(max_value=253402300799).map(datetime.fromtimestamp)
"""Strategy for generating `datetime` objects."""


commit_statuses = fixed_dictionaries(
    {'updated_at': datetimes,
     'state': text(),
     'context': text(),
     'target_url': text(),
     })
"""Strategy for generating GitHub commit status dicts."""


jenkins_results = sampled_from(merge_pr.JenkinsResults.iterconstants())
"""Strategy for generating JenkinsResults values."""


class StatusesTests(TestCase):
    """
    Tests for interpretation of commit statuses.

    https://developer.github.com/v3/repos/statuses/
    """

    @given(commit_statuses)
    def test_final_status_one(self, status):
        self.assertEqual(status, merge_pr.final_status([status]))

    @given(commit_statuses, commit_statuses)
    def test_final_status_many(self, status1, status2):
        target = status1
        if status2['updated_at'] > status1['updated_at']:
            target = status2
        self.assertEqual(target, merge_pr.final_status([status2, status1]))

    @given(commit_statuses)
    def test_not_success(self, status):
        assume(status['state'] != u"success")
        self.assertEqual(True, merge_pr.not_success(status))

    @given(commit_statuses)
    def test_not_success_success(self, status):
        status['state'] = u"success"
        self.assertEqual(False, merge_pr.not_success(status))

    @given(commit_statuses, jenkins_results)
    def test_format_status(self, status, jenkins):
        formatted = merge_pr.format_status((status, jenkins))
        self.assertIsInstance(formatted, unicode)
        self.assertIn(status['context'], formatted)
        self.assertIn(status['target_url'], formatted)


# These strategies are far from complete coverage of the possible
# Jenkins API responses.

jenkins_builds = fixed_dictionaries(dict(
    result=sampled_from([None, 'FAILURE', 'ABORTED', 'SUCCESS'])))
"""Strategy for generating records of individual builds of a Jenkins job."""


jenkins_build_result_with_builds = fixed_dictionaries(dict(
    inQueue=booleans(),
    builds=lists(jenkins_builds),
    property=dictionaries(text(), text())))
"""Strategy for generating Jenkins API information for a job with builds."""

jenkins_build_result_with_no_builds = fixed_dictionaries(dict(
    inQueue=booleans()))
"""Strategy for generating Jenkins API information for a job with no builds."""

jenkins_build_results = one_of(
    jenkins_build_result_with_builds,
    jenkins_build_result_with_no_builds,
    just(pmap()))
"""Strategy for generating Jenkins API information for a job."""


class JenkinsResultsTests(TestCase):
    """
    Tests for interpretation of build results from Jenkins.
    """

    @given(jenkins_build_results)
    def test_result_types(self, info):
        result, params = merge_pr.jenkins_info_from_response(info)
        self.assertIn(result, list(merge_pr.JenkinsResults.iterconstants()))
        if params is not None:
            self.assertIsInstance(params, dict)

    @given(jenkins_build_results)
    def test_in_queue(self, info):
        info = dict(info)
        info['inQueue'] = True
        result, params = merge_pr.jenkins_info_from_response(info)
        self.assertEqual(merge_pr.JenkinsResults.RUNNING, result)
        self.assertEqual({}, params)

    @given(jenkins_build_results)
    def test_builds_not_present(self, info):
        assume(not info.get('inQueue', False))
        info = dict(info)
        if 'builds' in info:
            del info['builds']
        result, params = merge_pr.jenkins_info_from_response(info)
        self.assertEqual(merge_pr.JenkinsResults.UNKNOWN, result)
        self.assertEqual({}, params)

    @given(jenkins_build_results)
    def test_no_builds(self, info):
        assume(not info.get('inQueue', False))
        info = dict(info)
        info['builds'] = []
        result, params = merge_pr.jenkins_info_from_response(info)
        self.assertEqual(merge_pr.JenkinsResults.NOTRUN, result)
        self.assertEqual({}, params)
