#!/usr/bin/env python
# Copyright ClusterHQ Inc.  See LICENSE file for details.
# coding: utf-8

"""
Loop until the checks for a PR are all green, then optionally merge
the PR.
"""

from __future__ import print_function

from argparse import (
    ArgumentParser,
    RawDescriptionHelpFormatter,
    )
from collections import Counter
from functools import partial
from itertools import count
import json
from operator import itemgetter
import os
import sys
import time
import urlparse

import requests
from requests.auth import HTTPBasicAuth
from twisted.python.constants import Values, ValueConstant

API_BASE_URL = 'https://api.github.com/'
REPOS_API_PATH = 'repos'

GITHUB_USERNAME_ENV_VAR = 'GITHUB_USER'
GITHUB_TOKEN_ENV_VAR = 'GITHUB_TOKEN'

JENKINS_USERNAME_ENV_VAR = 'JENKINS_USER'
JENKINS_PASSWORD_ENV_VAR = 'JENKINS_PASSWORD'

MINIMUM_STATUSES = 50
MAX_RETRIES = 1
SLEEP_FOR = 60

GITHUB_VARS_REQUIRED = """You must set {} and {}.
You can generate a token at https://github.com/settings/tokens
(this script requires the repo:status and public_repo scopes)
""".format(GITHUB_USERNAME_ENV_VAR, GITHUB_TOKEN_ENV_VAR)

JENKINS_VARS_REQUIRED = """\
Please specify the jenkins user and password in the {} and {} env vars.
""".format(JENKINS_USERNAME_ENV_VAR, JENKINS_PASSWORD_ENV_VAR)

DESCRIPTION = """Merge a branch when all the tests pass.

Given the URL to a pull request on GitHub this script will
loop until all the tests pass, and then merge the branch.

It will retry failures on Jenkins, and will also respond
to any retries you make yourself, and cope with the branch
being updated while it is running, waiting for the tests
to pass for the new HEAD.

It can optionally skip the merge if you just want to know
when all the tests pass.

It requires the following environment variables to be set:
""" + GITHUB_VARS_REQUIRED + "\n" + JENKINS_VARS_REQUIRED

JENKINS_BUILD_INFO_PATH = (
    '/api/json?tree=inQueue,builds[result],'
    'property[parameterDefinitions[name,defaultParameterValue[value]]]'
)


def url_path(url):
    """
    Return the path portion of a URL.

    :param unicode url: the URL.
    :return unicode: the path portion of the input URL.
    """
    return urlparse.urlsplit(url).path


def url_path_parts(url):
    """
    Return the path segments of a URL.

    http://example.com/foo/bar/baz -> ['foo', 'bar', 'baz']

    :param unicode url: the URL.
    :return Sequence[unicode]: the segments of the path
        of the input url.
    """
    return url_path(url).split('/')


def replace(a, b, x):
    """
    return x, unless x == a then return b

    l2 = map(partial(replace, a, b), l1)

    l2 will be the same as l1, except that anything
    equal to a will have been replaced by b.

    map(partial(replace, 1, 2), [1, 2, 3]) == [2, 2, 3]
    """
    return (b if x == a else x)


def pr_api_url_from_web_url(url):
    """
    get the api url for a pull request from the web one.

    :param unicode url: the web URL of the pull request.
    :return unicode: the API URL of the same pull request.
    """
    path = '/'.join(
        map(partial(replace, 'pull', 'pulls'),
            url_path_parts(url))
    )
    return API_BASE_URL + REPOS_API_PATH + path


def fetch_page(base_url, page, session):
    """
    Fetch a particular page number for a GitHub API resource.

    :param unicode base_url: the URL of the GitHub API resource.
    :param int page: the page number to request (0 indexed).
    :param requests.Session session: the requests Session to use for
        the request.
    :return dict: The deserialized response content from GitHub.
    """
    return session.get(base_url + "?page={}".format(page)).json()


def final_status(statuses):
    """
    Get the most recent entry for a list of GitHub statuses.

    :param Iterable[dict] statuses: the statuses.
    :return dict: the last of the input statues by updated_at key.
    """
    return sorted(statuses, key=itemgetter('updated_at'))[-1]


def not_success(status):
    """
    Whether the GitHub status is not a success.

    :param dict status: a GitHub API status.
    :return bool: whether the status isn't a success
    """
    return status['state'] != u'success'


def format_status(status):
    """
    Format a GitHub status for presentation.

    :param (dict, JenkinsResult) status: a GitHub API status
        and Jenkins build result.
    :return unicode: a string formatting of the pair
         for display to the user.
    """
    github, jenkins = status
    return u"{}: {} ({})".format(
        github['context'], jenkins.value, github['target_url'])


def infinite_sleeps(sleep_for):
    """
    Generator that will sleep between each yield.

    :param int sleep_for: How long to sleep between
         each iteration.
    :return Iterable[None]: iterable that will sleep for
        `sleep_for` between each item.
    """
    for i in count():
        yield i
        time.sleep(sleep_for)


def delete_branch(pr, session):
    """
    Delete the source branch of a pull request using the API.

    :param dict pr: the GitHub API pull request representation.
    :param requests.Session session: the requests Session to use
        for the request.
    :return requests.Response: the response from GitHub.
    """
    refs_url = pr['head']['repo']['git_refs_url']
    branch_url = refs_url.replace('{/sha}', '/heads/' + pr['head']['ref'])
    return session.delete(branch_url)


def get_statuses(pr, session):
    """
    Get all of the statuses for a pull request.

    This takes care of pagination, and deduplicating the
    entries.

    :param dict pr: the GitHub API pull request representation.
    :param requests.Session session: the requests Session to use
        for the requests.
    :return Iterable[dict]: an iterable of GitHub status dicts.
    """
    base_url = pr['_links']['statuses']['href']
    statuses = []
    for i in count():
        new_statuses = fetch_page(base_url, i, session)
        if not new_statuses or 'context' not in new_statuses[0]:
            break
        statuses.extend(new_statuses)

    # I think we slightly abuse the status api, instead
    # of updating existing statuses, we add new ones
    # each time the state changes. We take the latest
    # of each context and use that.
    by_context = {}
    for s in statuses:
        by_context.setdefault(s['context'], []).append(s)

    return map(final_status, by_context.values())


class JenkinsResults(Values):
    """
    The outcome of a Jenkins build.
    """
    RUNNING = ValueConstant('running')
    PASSED = ValueConstant('success')
    FAILED = ValueConstant('failed')
    NOTRUN = ValueConstant('notrun')
    # Sometimes Jenkins replies with not much info,
    # e.g. no 'builds' in the result just after a
    # build finished. We use this status if that
    # happens so we can ignore the build for that
    # cycle
    UNKNOWN = ValueConstant('unknown')


def jenkins_result_from_api(result):
    """
    Convert a Jenkins job result in to a value from JenkinsResults.

    :param unicode result: the result of the job from the Jenkins API.
    :return JenkinsResults: the corresponding JenkinsResults value.
    """
    if result is None:
        return JenkinsResults.RUNNING
    elif result in ['FAILURE', 'ABORTED']:
        return JenkinsResults.FAILED
    elif result == 'SUCCESS':
        return JenkinsResults.PASSED
    else:
        raise AssertionError(
            "Don't know how to handle Jenkins result {}".format(result))


def properties_to_params(props):
    """
    Given Jenkins build properties, return the default parameters.

    The default parameters are in the form that can be used to start
    a build with those parameters.

    :param Iterable[dict]: a list of properties for a job from the Jenkins API.
    :return dict or None: the default params for the job if any, or
        None if there aren't any parameters.
    """
    candidates = filter(lambda x: 'parameterDefinitions' in x, props)
    if candidates:
        def transform(x):
            return {x['name']: x['defaultParameterValue']['value']}
        return {
            k: v
            for d in map(transform, candidates[0]['parameterDefinitions'])
            for k, v in d.items()
        }
    return None


def jenkins_info_from_response(project):
    """
    Get the Jenkins job information from the Jenkins API response.

    :param dict project: the API response as a dict.
    :return (JenkinsResults, dict): The first element will
        be a JenkinsResults value corresponding to the status
        of the job. The second element will be
        the parameters to start a new Jenkins build if needed.
    """
    if project.get('inQueue', False):
        return JenkinsResults.RUNNING, {}
    if 'builds' not in project:
        return JenkinsResults.UNKNOWN, {}
    if len(project['builds']) < 1:
        return JenkinsResults.NOTRUN, {}
    result = jenkins_result_from_api(project['builds'][0]['result'])
    return result, properties_to_params(project['property'])


def get_jenkins_info(jenkins_session, status):
    """
    Get the Jenkins job info for a GitHub status, if any.

    :param requests.Session jenkins_session: the requests Session to
        use to make requests.
    :param dict status: the GitHub status.
    :return (JenkinsResults, dict): The first element will
        be a JenkinsResults value if the information can
        be found, None if not. The second element will be
        the parameters to start a new Jenkins build if needed.
    """
    if status['context'].startswith('jenkins-'):
        jenkins_url = status['target_url']
        project = jenkins_session.get(
            jenkins_url + JENKINS_BUILD_INFO_PATH).json()
        return jenkins_info_from_response(project)
    return None, None


def retry(jenkins_session, url, params):
    """
    Retry a Jenkins job.

    :param unicode url: the url of the job.
    :param dict params: the params to use to start the new build,
        if any.
    """
    print("Retrying {}".format(url))
    if params:
        jenkins_session.post(url + '/buildWithParameters', data=params)
    else:
        jenkins_session.post(url + '/build')


def do_merge(pr_url, pr, session):
    """
    Attempt a merge using the GitHub API then delete the source branch.

    :param unicode pr_url: the URL of the pull request.
    :param dict pr: the pull request API dict.
    :param requests.Session session: the requests Session to
        use for the request.
    :return bool: True if everything worked, False if not.
    """
    response = session.put(
        pr_url + '/merge',
        data=json.dumps(dict(sha=pr['head']['sha'])))
    if response.status_code != 200:
        print("PR failed to merge: {}".format(response.json()['message']))
        return False
    else:
        print("{} at {}".format(
            response.json()['message'], response.json()['sha']))
        del_resp = delete_branch(pr, session)
        if del_resp.status_code != 204:
            print("Branch deletion failed: {}".format(del_resp.content))
            return False
    print("Branch deleted")
    return True


def maybe_retry_jobs(statuses, retry_counts, max_retries, jenkins_session):
    """
    Maybe trigger some retries on Jenkins.

    Given a list of statuses that aren't successful, see if there
    are any Jenkins jobs that can be retried that might make them
    successful.

    It won't retry the same job more than `max_retries` times.

    :param Iterable[dict] statuses: a list of GitHub statuses that
        aren't successful.
    :param dict retry_counts: the number of times each status has
        been retried already.
    :param int max_retries: the maximum number of times that a single
        job should be retried.
    :param request.Session jenkins_session: the requests.Session to
        use to make any requests to Jenkins.
    """
    jenkins_statuses = map(
        partial(get_jenkins_info, jenkins_session),
        statuses)
    map(print,
        map(format_status,
            zip(statuses, map(itemgetter(0), jenkins_statuses))))
    candidates = filter(
        lambda x: x[1][0] in [JenkinsResults.FAILED, JenkinsResults.NOTRUN],
        zip(statuses, jenkins_statuses))

    def exceeded_retries(context):
        return retry_counts[context] > max_retries
    retried_too_many = filter(
        lambda x: exceeded_retries(x[0]['context']), candidates)

    def format_retried_to_many(job):
        return (
            "{} retried {} times and still failing, not retrying. You can "
            "look at the build and retry yourself if it is a spurious "
            "problem, and this script will notice that you have done so."
        ).format(job['target_url'], retry_counts[job['context']])

    map(print, map(lambda x: format_retried_to_many(x[0]), retried_too_many))
    to_retry = filter(lambda x: x not in retried_too_many, candidates)
    for job in to_retry:
        retry(jenkins_session, job[0]['target_url'], job[1][1])
        retry_counts[job[0]['context']] += 1


def loop_until_passed(
    pr_url, sleep_between, session, jenkins_session, max_retries
):
    """
    Loop until all the statuses for the target pull request are green.

    :param unicode pr_url: the API URL of the pull request to watch.
    :param int sleep_between: the number of seconds to sleep between
        checking whether all the statuses are green.
    :param requests.Session session: the session to use to communicate
        with GitHub.
    :param requests.Session jenkins_session: the session to sue to
        communicate with Jenkins.
    :param int max_retries: the maximum number of retries for any
        single Jenkins job.
    :return (dict, Iterable[dict]): if all the statuses are green,
        the first element is the GitHub pull request API representation,
        the second is the list of the GitHub status API representations
        for that pull request. If the statuses aren't all green
        but the loop wants to exit for some reason (maybe the PR
        was deleted) then the first element of the tuple will
        be None.
    """
    retry_counts = Counter()
    for _ in infinite_sleeps(sleep_between):
        resp = session.get(pr_url)
        if resp.status_code != 200:
            print("PR not found: {}".format(resp.content))
            return None, None
        pr = resp.json()
        if pr['state'] != u'open':
            print("Merge request not open: {}".format(pr['state']))
            return None, None
        else:
            statuses = get_statuses(pr, session)
            if len(statuses) < MINIMUM_STATUSES:
                print((
                    "Can't merge PR yet because there aren't "
                    "enough statuses reporting ({} so far)").format(
                    len(statuses)))
            else:
                needed = filter(not_success, statuses)
                if not needed:
                    return pr, statuses
                print(
                    "Can't merge PR yet because these {} "
                    "checks haven't succeeded:".format(len(needed)))
                maybe_retry_jobs(
                    needed, retry_counts, max_retries, jenkins_session)
        print(
            "Sleeping for {} seconds and trying again.\n\n".format(
                sleep_between))


def main(args):
    """
    Perform the function of the script.

    :param Iterable[unicode] args: the command-line arguments for this run.
    :return int: The recommended return code of the process.
    """
    argparse = ArgumentParser(description=DESCRIPTION,
                              formatter_class=RawDescriptionHelpFormatter)
    argparse.add_argument('url', help="URL of the PR to merge")
    argparse.add_argument(
        '--no-merge', help="Don't merge, just wait until tests pass",
        action='store_true', default=False)
    argparse.add_argument(
        '--max-retries',
        help="Number of times a single job can be automatically retried.",
        type=int, default=MAX_RETRIES)
    opts = argparse.parse_args(args)
    username = os.environ.get(GITHUB_USERNAME_ENV_VAR, None)
    token = os.environ.get(GITHUB_TOKEN_ENV_VAR, None)
    if username is None or token is None:
        sys.stderr.write(GITHUB_VARS_REQUIRED)
        return 1
    session = requests.Session()
    session.auth = HTTPBasicAuth(username, token)
    jenkins_username = os.environ.get(JENKINS_USERNAME_ENV_VAR, None)
    jenkins_password = os.environ.get(JENKINS_PASSWORD_ENV_VAR, None)
    if jenkins_username is None or jenkins_password is None:
        sys.stderr.write(JENKINS_VARS_REQUIRED)
        return 1
    jenkins_session = requests.Session()
    jenkins_session.auth = HTTPBasicAuth(jenkins_username, jenkins_password)
    pr_url = pr_api_url_from_web_url(opts.url)
    pr, statuses = loop_until_passed(
        pr_url, SLEEP_FOR, session, jenkins_session, opts.max_retries)
    if pr is None:
        return 1
    if not opts.no_merge:
        print("Attempting merge as {} checks passed".format(len(statuses)))
        if not do_merge(pr_url, pr, session):
            return 1
    return 0
