# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Submit benchmark results to a server.
"""

from __future__ import print_function

import json
import sys

from twisted.internet import endpoints
from twisted.internet.defer import succeed
from twisted.internet.task import react
from twisted.python import usage
from twisted.web import client, http
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer

from zope.interface import implementer


@implementer(IBodyProducer)
class StringProducer(object):
    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


def submit(agent, result):
    """
    Post the given result using the given agent.

    :param Agent agent: The HTTP client agent.
    :param dict result: The JSON-compatible result.
    :return: Deferred that fires when a reponse from the server is received.
    """
    body = StringProducer(json.dumps(result))
    req = agent.request(
        "POST",
        "/v1/benchmark-results",
        headers=Headers({'Content-Type': ['application/json']}),
        bodyProducer=body
    )

    def get_response_body(response):
        d = client.readBody(response)
        d.addCallback(lambda body: (response, body))
        return d

    req.addCallback(get_response_body)

    def process_response(response_and_body):
        (response, body) = response_and_body
        if response.code != http.CREATED:
            print("Failed to submit the request", file=sys.stderr)
            print("{} {}".format(response.code, response.phrase),
                  file=sys.stderr)
        else:
            print("Successfully submitted the result")

        json_body = json.loads(body)

        if response.code != http.CREATED:
            print("Message: {}".format(json_body['message']), file=sys.stderr)
        else:
            print("Assigned result ID: {}".format(json_body['id']))

    req.addCallback(process_response)
    return req


class Options(usage.Options):
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
        sys.stderr.write(e.args[0])
        sys.stderr.write('\n\n')
        sys.stderr.write(options.getSynopsis())
        sys.stderr.write('\n')
        sys.stderr.write(options.getUsage())
        raise SystemExit(1)

    agent = client.ProxyAgent(
        endpoints.TCP4ClientEndpoint(
            reactor,
            options['address'],
            options['port'],
        ),
        reactor,
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

    return submit(agent, result)


if __name__ == '__main__':
    react(main, (sys.argv[1:],))
