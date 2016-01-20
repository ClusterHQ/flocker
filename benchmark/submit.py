# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Submit benchmark results to a server.
"""

from __future__ import print_function

import json
import sys

from twisted.internet.task import react
from twisted.python import usage
from twisted.web.http import CREATED

from treq import json_content, post


class SubmitFailure(Exception):
    def __init__(self, code, phrase, message):
        super(SubmitFailure, self).__init__(message)
        self.code = code
        self.phrase = phrase

    def __str__(self):
        return "[{} {}] {}".format(self.code, self.phrase, self.message)


def submit(server_url, result):
    """
    Post the given result to the given server.

    :param str server_url: The server's URL.
    :param dict result: The JSON-compatible result.
    :return: Deferred that fires with an ID of the submitted result on success
        or with SubmitFailure if the result is rejected by the server.

    This function may also return any of the ``treq`` failures.
    """
    req = post(
        server_url + "/v1/benchmark-results",
        json.dumps(result),
        headers=({'Content-Type': ['application/json']}),
    )

    def get_response_content(response):
        d = json_content(response)
        d.addCallback(lambda content: (response, content))
        return d

    req.addCallback(get_response_content)

    def process_response(response_and_content):
        (response, content) = response_and_content
        if response.code != CREATED:
            raise SubmitFailure(response.code, response.phrase,
                                content['message'])
        else:
            return content['id']

    req.addCallback(process_response)
    return req


class Options(usage.Options):
    longdesc = ("Submit a benchmark result provided as a JSON document "
                "on the standard input to the benchmark server.")

    optParameters = [
        ['address', None, None, "The address of the benchmark server."],
        ['port', None, 8888, "The port of the benchmark server.", int],
    ]

    def postOptions(self):
        if self.get('address') is None:
            raise usage.UsageError("The address must be specified.")


def main(reactor, args):
    try:
        options = Options()
        options.parseOptions(args)
    except usage.UsageError as e:
        print(e.args[0], file=sys.stderr)
        print('', file=sys.stderr)
        print(str(options), file=sys.stderr)
        raise SystemExit(1)

    server_url = b"http://{}:{}".format(
        options['address'], options['port'],
    )

    try:
        result_input = sys.stdin.read()
        result = json.loads(result_input)
    except ValueError as e:
        print(result_input, file=sys.stderr)
        print(
            "Standard input is not valid JSON document: {}".format(e.message),
            file=sys.stderr,
        )
        raise SystemExit(1)

    d = submit(server_url, result)

    def succeeded(id):
        print("Assigned result ID: {}".format(id))

    def failed(failure):
        failure.trap(SubmitFailure)
        print("Failed to submit the result: {}".format(failure.value),
              file=sys.stderr)
        raise SystemExit(1)

    d.addCallbacks(succeeded, failed)
    return d


if __name__ == '__main__':
    react(main, (sys.argv[1:],))
