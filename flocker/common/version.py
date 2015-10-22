# -*- test-case-name: flocker.common.test.test_version -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

import re

from characteristic import attributes, Attribute

from pyrsistent import PRecord, field


# This regex parses valid version numbers for Flocker. It handles two
# versioning schemes (legacy and PEP440 compliant). In particular, it
# parses the trailing part of the version added by Versioneer 0.10 and
# 0.15.
_VERSION_RE = re.compile(
    # The base version
    r"(?P<major>[0-9]+)\.(?P<minor>[0-9]+)\.(?P<micro>[0-9]+)"
    # Pre-release
    # Legacy versions used `preN` instead of `rcN`
    r"((?:rc|pre)(?P<pre_release>[0-9]+))?"
    # Weekly release
    # Legacy versions used `devN` instead of `.devN`
    r"(\.?dev(?P<weekly_release>[0-9]+))?"
    # The documentation release
    # Legacy versions used `+docN` instead of `.postN`
    r"((:?\.post|\+doc)(?P<documentation_revision>[0-9]+))?"
    # Development version
    # Legacy versions used `.` here if `+doc` was also present.
    r"([+.](?P<commit_count>[0-9]+).g(?P<commit_hash>[0-9a-f]+))?"
    # Whether the source tree is dirty (changed from the last commit).
    r"((?P<dirty>.dirty))?"
    # Always match the entire version string.
    r"$"
    )


class UnparseableVersion(Exception):
    """
    A version was passed that was unable to be parsed.
    """


class NotAPreRelease(Exception):
    """
    A version was passed that was not a pre-release.
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
            return self.release + '.dev' + self.weekly_release
        elif self.pre_release is not None:
            return self.release + 'rc' + self.pre_release
        return self.release


def _parse_version(version):
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
    parsed_version = _parse_version(version)
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
    parsed_version = _parse_version(version)
    return parsed_version.installable_release


def is_release(version):
    """
    Return whether the version corresponds to a marketing or documentation
    release.

    :param bytes version: A version of flocker.
    :return bool: Whether the version corresponds to a marketing or
        documentation release.
    """
    parsed_version = _parse_version(version)
    return (parsed_version.commit_count is None
            and parsed_version.pre_release is None
            and parsed_version.weekly_release is None
            and parsed_version.dirty is None)


def is_weekly_release(version):
    """
    Return whether the version corresponds to a weekly release.

    :param bytes version: A version of flocker.
    :return bool: Whether the version is a weekly release.
    """
    parsed_version = _parse_version(version)
    return (parsed_version.weekly_release is not None
            and parsed_version.commit_count is None
            and parsed_version.pre_release is None
            and parsed_version.dirty is None)


def is_pre_release(version):
    """
    Return whether the version corresponds to a pre-release.

    :param bytes version: A version of flocker.
    :return bool: Whether the version is a pre-release.
    """
    parsed_version = _parse_version(version)
    return (parsed_version.pre_release is not None
            and parsed_version.weekly_release is None
            and parsed_version.commit_count is None
            and parsed_version.dirty is None)


def get_pre_release(version):
    """
    Return the number of a pre-release.

    :param bytes version: A pre-release version of Flocker.
    :return int: The number of the pre-release.

    :raises UnparseableVersion: If the version is not a pre-release.
    """
    if not is_pre_release(version):
        raise NotAPreRelease(version)

    parsed_version = _parse_version(version)

    return int(parsed_version.pre_release)


def target_release(version):
    """
    Return the target final release for a pre-release.

    :param bytes version: A pre-release version of Flocker.
    :return bytes: The final marketing version the pre-release is for.

    :raises NotAPreRelease: If the version is not a pre-release.
    """
    if not is_pre_release(version):
        raise NotAPreRelease(version)

    parsed_version = _parse_version(version)

    return parsed_version.release


def get_package_key_suffix(version):
    """
    Return the suffix for the keys in which packages for a given version are
    stored.

    :param bytes version: A version of Flocker.
    :return bytes: The suffix for the keys in which packages for a version are
        stored.
    """
    if is_release(version):
        return ""
    else:
        return "-testing"


class RPMVersion(PRecord):
    """
    An RPM compatible version and a release version.
    See: http://fedoraproject.org/wiki/Packaging:NamingGuidelines#Pre-Release_packages  # noqa

    :ivar bytes version: An RPM compatible version.
    :ivar bytes release: An RPM compatible release version.
    """
    version = field(mandatory=True)
    release = field(mandatory=True)


def make_rpm_version(flocker_version):
    """
    Parse the Flocker version generated by versioneer into a
    :class:`RPMVersion`.

    :param flocker_version: The versioneer style Flocker version string.
    :return: An ``RPMVersion``.
    """
    parsed_version = _parse_version(flocker_version)
    installable = parsed_version.installable_release

    # Given pre or dev number X create a 0 prefixed, `.` separated
    # string of version labels. E.g.
    # 0.1.2rc2  becomes
    # 0.1.2-0.rc.2
    if is_pre_release(installable):
        release = ['0', 'rc', parsed_version.pre_release]
    elif is_weekly_release(installable):
        release = ['0', 'dev', parsed_version.weekly_release]
    else:
        release = ['1']

    # The version may also contain a distance, shortid which
    # means that there have been changes since the last
    # tag. Additionally there may be a ``dirty`` suffix which
    # indicates that there are uncommitted changes in the
    # working directory.  We probably don't want to release
    # untagged RPM versions, and this branch should probably
    # trigger and error or a warning. But for now we'll add
    # that extra information to the end of release number.
    # See https://clusterhq.atlassian.net/browse/FLOC-833
    if parsed_version.commit_count is not None:
        release += [
            parsed_version.commit_count, 'g' + parsed_version.commit_hash]
    if parsed_version.dirty:
        release.append('dirty')

    return RPMVersion(
        version=parsed_version.release, release='.'.join(release))
