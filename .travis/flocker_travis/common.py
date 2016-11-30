#!/usr/bin/env python2
#
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Run a build step.

Travis calls this during the `script` phase of its build lifecycle.
 * https://docs.travis-ci.com/user/customizing-the-build

Set ``FLOCKER_BUILDER`` environment variable before calling this script.
"""
from functools import partial
from os import environ


class BuildHandler(object):
    def __init__(self, handlers, default_handler=None):
        self._handlers = handlers
        self._default_handler = default_handler

    def _get_handler(self, build_label):
        arguments = []
        parts = build_label.split(":")
        while True:
            key = ":".join(parts)
            handler = self._handlers.get(key)
            if handler:
                break
            arguments.append(
                parts.pop()
            )
        else:
            raise KeyError("Handler not found", build_label, self._handlers)

        return partial(handler, *reversed(arguments))

    def main(self):
        build_label = environ["FLOCKER_BUILDER"]
        handler = self._get_handler(build_label)
        return handler()
