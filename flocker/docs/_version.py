# -*- test-case-name: flocker.docs.test.test_version -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

import re

_VERSION_RE = re.compile('(?P<base>.*?)(\+doc\.(?P<doc>[0-9]+))?$')


def get_version(version):
    match = _VERSION_RE.match(version)
    return match.group('base')
