# -*- test-case-name: flocker.docs.test.test_version -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

import re

from characteristic import attributes, Attribute

_VERSION_RE = re.compile(
    # The base version
    r"(?P<major>[0-9])\.(?P<minor>[0-9]+)\.(?P<micro>[0-9]+)"
    # Pre-release
    r"(pre(?P<pre_release>[0-9]+))?"
    # Weekly release
    r"(dev(?P<weekly_release>[0-9]+))?"
    # The documentation release
    r"(\+doc(?P<documentation_revision>[0-9]+))?"
    # Development version
    r"(-(?P<commit_count>[0-9]+)-g(?P<commit_hash>[0-9a-f]+))?"
    # Wether the tree is dirty.
    r"((?P<dirty>-dirty))?"
    # Always match the entire version string.
    r"$"
    )


class UnparseableVersion(Exception):
    """
    A version was passed that was unable to be parsed.
    """


@attributes([
    'major',
    'minor',
    'micro',
    Attribute('pre_release', default_value=None),
    Attribute('weekly_release', default_value=None),
    Attribute('documentation_revision', default_value=None),
    Attribute('commit_count', default_value=None),
    Attribute('commit_hash', default_value=None),
    Attribute('dirty', default_value=None),
])
class FlockerVersion(object):
    """
    A version of Flocker.

    :ivar str major: The major number of the (most recent) release.
    :ivar str minor: The minor number of the (most recent) release.
    :ivar str micro: The micro number of the (most recent) release.
    :ivar str pre_release: The number of the (most recent) pre-release,
        or ``None`` if there hasn't been a pre release.
    :ivar str weekly_release: The number of the (most recent) weekly release,
        or ``None`` if there hasn't been a weekly release.
    :ivar str documentation_revision: The documentation revision of the
        (most recent) release or ``None`` if there hasn't been a documentation
        release.
    :ivar str commit_count: The number of commits since the last release or
        ``None`` if this is a release.
    :ivar str commit_hash: The hash of the current commit, or ``None`` if this
        is a release.
    :ivar str dirty: If the tree is dirty, the string '-dirty'.
        Otherwise, ``None``.
    """

    @property
    def release(self):
        """
        The version string of the last full marketing release.
        """
        return "%s.%s.%s" % (self.major, self.minor, self.micro)

    @property
    def installable_release(self):
        """
        The version string of the last release of Flocker which can be
        installed (CLI or node package). These are updated for marketing
        releases, pre-releases and weekly releases but not documentation
        releases.
        """
        if self.weekly_release is not None:
            return self.release + 'dev' + self.weekly_release
        elif self.pre_release is not None:
            return self.release + 'pre' + self.pre_release
        return self.release


def parse_version(version):
    """
    Parse a version of Flocker.

    :return FlockerVersion: The parsed version.

    :raises UnparseableVersion: If the version can't be parsed as a Flocker
        version.
    """
    match = _VERSION_RE.match(version)
    if match is None:
        raise UnparseableVersion(version)
    parts = match.groupdict()
    return FlockerVersion(**parts)


def get_doc_version(version):
    """
    Get the version string of Flocker to display in documentation.
    """
    parsed_version = parse_version(version)
    if (is_release(version)
            and parsed_version.documentation_revision is not None):
        return parsed_version.release
    else:
        return version


def get_installable_version(version):
    """
    Get the version string of the latest version of Flocker which can be
    installed (CLI and node).
    """
    parsed_version = parse_version(version)
    return parsed_version.installable_release


def is_release(version):
    """
    Return whether the version corresponds to a marketing or documentation
    release.
    """
    parsed_version = parse_version(version)
    return (parsed_version.commit_count is None
            and parsed_version.pre_release is None
            and parsed_version.weekly_release is None
            and parsed_version.dirty is None)


def is_weekly_release(version):
    """
    Return whether the version corresponds to a weekly release.

    :param bytes version: A version of flocker.

    :return bool: Wether the version is a weekly release.
    """
    parsed_version = parse_version(version)
    return (parsed_version.weekly_release is not None
            and parsed_version.commit_count is None
            and parsed_version.pre_release is None
            and parsed_version.dirty is None)
