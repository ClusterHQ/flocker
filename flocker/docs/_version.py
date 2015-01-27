# -*- test-case-name: flocker.docs.test.test_version -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

import re

_VERSION_RE = re.compile(
    # The base version (in 'release')
    r"(?P<release>[0-9]\.[0-9]+\.[0-9]+)"
    # For a documentation release, the release number.
    # (in 'doc-release').
    r"(\+doc\.(?P<doc>[0-9]+))?"
    # For development version, the number of commits since the last
    # release and git hash
    r"((?P<development>-[0-9]+-g[0-9a-f]+))?"
    # Wether the tree is dirty.
    r"((?P<dirty>-dirty))?"
    # Always match the entire version string.
    r"$"
    )


class UnparseableVersion(Exception):
    """
    A version was passed that was unable to be parsed.
    """


def parse_version(version):
    """
    Parse a flocker version.

    :return dict: with the following keys. If a key isn't relevant, the value
        is ``None``.

        release
            The base release
        development
            For development versions, the number of commits since the last
            release and the commit hash, in the format used by ``git describe`.
        doc
            For a documentation only release, the relase number.
        dirty
            If the tree is dirty, the string '-dirty'.

    :raises UnparseableVersion: If the version can't be parsed as a flocker
        version.
    """
    match = _VERSION_RE.match(version)
    if match is None:
        raise UnparseableVersion(version)
    return match.groupdict()


def get_doc_version(version):
    parts = parse_version(version)
    if is_release(version) and parts['doc'] is not None:
        return parts['release']
    else:
        return version


def is_release(version):
    parts = parse_version(version)
    return (parts['development'] is None and parts['dirty'] is None)
