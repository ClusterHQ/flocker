"""
Interface with Flocker using mount and umount (by way of the Docker plugin).

No Docker required, though.
"""

import sys
from json import dumps
from subprocess import check_call

from twisted.internet.endpoints import UNIXClientEndpoint
from twisted.internet.defer import inlineCallbacks
from twisted.web.client import ProxyAgent
from twisted.internet.task import react

from treq.client import HTTPClient
from treq import json_content

from ._script import PLUGIN_PATH


JSON = {'Content-Type': ['application/json']}


@inlineCallbacks
def mount(reactor, name, path):
    client = HTTPClient(
        ProxyAgent(UNIXClientEndpoint(reactor, PLUGIN_PATH.path), reactor))
    yield client.post("/VolumeDriver.Create",
                      dumps({"Name": name}),
                      headers=JSON)
    response = yield client.post("/VolumeDriver.Mount",
                                 dumps({"Name": name}),
                                 headers=JSON)
    response = yield json_content(response)
    if response["Err"]:
        print >> sys.stderr, response["Err"]
        raise SystemExit(1)
    mountpoint = response["Mountpoint"]
    check_call(["mount", "--bind", mountpoint, path])


def main():
    if not len(sys.argv) == 3:
        print >> sys.stderr, "Usage: mount.flocker <name> <path>"
        raise SystemExit(2)
    react(mount, sys.argv[1:])

if __name__ == '__main__':
    main()
