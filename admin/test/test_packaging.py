# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.packaging``.
"""
from collections import namedtuple
from glob import glob
from subprocess import check_output, CalledProcessError
import sys
from textwrap import dedent
from unittest import skipIf

from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.python.usage import UsageError
from twisted.trial.unittest import TestCase

from flocker.testtools import FakeSysModule

from ..packaging import (
    sumo_package_builder, InstallVirtualEnv, InstallApplication, BuildPackage,
    BuildSequence, BuildOptions, BuildScript, GetPackageVersion,
    DelayedRpmVersion, FLOCKER_DEPENDENCIES_RPM, FLOCKER_DEPENDENCIES_DEB,
    CreateLinks, _native_package_type
)
from ..release import make_rpm_version, rpm_version

FLOCKER_PATH = FilePath(__file__).parent().parent().parent()

# XXX: Get fpm installed on the build slaves.
# See https://github.com/ClusterHQ/build.clusterhq.com/issues/32
require_fpm = skipIf(not which('fpm'), "Tests require the `fpm` command.")

PLATFORM_PACKAGE_TYPE = _native_package_type()
require_rpm = skipIf(PLATFORM_PACKAGE_TYPE != 'rpm',
                     "Tests require an `rpm` based platform. Found {}.".format(
                         PLATFORM_PACKAGE_TYPE))
require_deb = skipIf(PLATFORM_PACKAGE_TYPE != 'deb',
                     "Tests require a `deb` based platform. Found {}.".format(
                         PLATFORM_PACKAGE_TYPE))

def assert_equal_steps(test_case, expected, actual):
    """
    Show inequalities in the steps of two ``BuildSequence`` instances.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :param expected: The expected build step instance.
    :param actual: The actual build step instance.
    :raises: ``TestFailure`` if the build steps are not equal, showing the
        unequal or missing steps.
    """
    expected_steps = getattr(expected, 'steps')
    actual_steps = getattr(actual, 'steps')
    if None in (expected_steps, actual_steps):
        test_case.assertEqual(expected, actual)
    else:
        mismatch_steps = []
        missing_steps = []
        for index, expected_step in enumerate(expected_steps):
            try:
                actual_step = actual_steps[index]
            except IndexError:
                missing_steps = expected_steps[index:]
                break
            if expected_step != actual_step:
                mismatch_steps.append('expected: {} != actual: {}'.format(
                    expected_step, actual_step))

        if mismatch_steps or missing_steps:
            test_case.fail(
                'Step Mismatch\n'
                'Mismatch: {}\n'
                'Missing: {}\n'.format(mismatch_steps, missing_steps)
            )


def assert_dict_contains(test_case, expected, actual, message=''):
    """
    Fail unless the supplied ``actual`` ``dict`` contains all the items in
    ``expected``.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :param expected: The expected build step instance.
    :param actual: The actual build step instance.
    """
    missing_items = []
    mismatch_items = []
    no_value = object()
    for key, expected_value in expected.items():
        actual_value = actual.get(key, no_value)
        if actual_value is no_value:
            missing_items.append(key)
        elif actual_value != expected_value:
            mismatch_items.append(
                '{}: {} != {}'.format(key, expected_value, actual_value)
            )
    if missing_items or mismatch_items:
        test_case.fail(
            '{}\n'
            'Missing items: {}\n'
            'Mismatch items:  {}\n'
            'Actual items: {}'.format(
                message, missing_items, mismatch_items, actual)
        )


def assert_rpm_headers(test_case, expected_headers, rpm_path):
    """
    Fail unless the ``RPM`` file at ``rpm_path`` contains all the
    ``expected_headers``.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :param dict expected_headers: A dictionary of header key / value pairs.
    :param FilePath rpm_path: The path to the RPM file under test.
    """
    output = check_output(
        ['rpm', '--query', '--info', '--package', rpm_path.path]
    )
    actual_headers = {}
    for line in output.splitlines():
        parts = [value.strip() for value in line.split(':', 1)]
        if len(parts) == 2:
            key, val = parts
            actual_headers[key] = val
        else:
            actual_headers[key] += parts[0]

    assert_dict_contains(
        test_case, expected_headers, actual_headers, 'Missing RPM Headers: '
    )


def assert_deb_headers(test_case, expected_headers, package_path):
    """
    Fail unless the ``deb`` file at ``package_path`` contains all the
    ``expected_headers``.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :param dict expected_headers: A dictionary of header key / value pairs.
    :param FilePath package_path: The path to the deb file under test.
    """
    output = check_output(
        ['dpkg', '--info', package_path.path]
    )
    actual_headers = {}
    key = None
    for line in output.splitlines():
        parts = [value.strip() for value in line.split(':', 1)]
        if len(parts) == 2:
            key, val = parts
            actual_headers[key] = val
        else:
            if key:
                actual_headers[key] += parts[0]
            else:
                key = None

    assert_dict_contains(
        test_case, expected_headers, actual_headers, 'Missing dpkg Headers: '
    )


def assert_rpm_requires(test_case, expected_requirements, rpm_path):
    """
    Fail unless the ``RPM`` file at ``rpm_path`` has all the
    ``expected_requirements``.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :param list expected_requirements: A list of requirement strings.
    :param FilePath rpm_path: The path to the RPM file under test.
    """
    output = check_output(
        ['rpm', '--query', '--requires', '--package', rpm_path.path]
    )
    actual_requirements = set(line.strip() for line in output.splitlines())
    expected_requirements = set(expected_requirements)
    missing_requirements = expected_requirements - actual_requirements
    if missing_requirements:
        test_case.fail('Missing requirements: {} in {}'.format(
            missing_requirements, rpm_path.path))


def fake_virtual_env(test_case):
    """
    Create a directory containing a fake pip executable which records its
    arguments when executed.

    Return an object containing methods with which to make assertions about the
    fake virtualenv.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :return: A ``Tester`` instance.
    """
    virtualenv_path = FilePath(test_case.mktemp())
    bin_path = virtualenv_path.child('bin')
    bin_path.makedirs()

    pip_log_path = virtualenv_path.child('pip.log')
    pip_log_path.setContent('')

    python_path = bin_path.child('python')
    FilePath(sys.executable).linkTo(python_path)

    pip_path = bin_path.child('pip')
    pip_path.setContent(
        dedent("""
        #!/usr/bin/env python
        import sys
        open({pip_log_path}, 'w').write('\\0'.join(sys.argv[1:]))
        """).lstrip().format(pip_log_path=repr(pip_log_path.path))
    )
    pip_path.chmod(0700)

    class Tester(object):
        path = virtualenv_path

        def assert_pip_args(self, expected_args):
            """
            `pip` was called with the `expected_args`.
            """
            test_case.assertEqual(
                expected_args,
                pip_log_path.getContent().strip().split('\0')
            )

    return Tester()


class SpyStep(object):
    """
    A build step which records the fact that it has been run.

    :ivar bool ran: ``False`` by default.
    """
    ran = False

    def run(self):
        self.ran = True


class BuildSequenceTests(TestCase):
    """
    Tests for ``BuildSequence``.
    """
    def test_run(self):
        """
        ``BuildSequence`` calls the ``run`` method of each of its ``steps``.
        """
        step1 = SpyStep()
        step2 = SpyStep()

        BuildSequence(steps=(step1, step2)).run()

        self.assertEqual((True, True), (step1.ran, step2.ran))


def assert_has_paths(test_case, expected_paths, parent_path):
    """
    Fail if any of the ``expected_paths`` are not existing relative paths of
    ``parent_path``.
    """
    missing_paths = []
    for path in expected_paths:
        if not parent_path.preauthChild(path).exists():
            missing_paths.append(path)
        if missing_paths:
            test_case.fail('Missing paths: {}'.format(missing_paths))


class InstallVirtualEnvTests(TestCase):
    """
    Tests for ``InstallVirtualEnv``.
    """
    def test_run(self):
        """
        ``InstallVirtualEnv.run`` installs a virtual python environment in its
        ``target_path``.
        """
        target_path = FilePath(self.mktemp())
        InstallVirtualEnv(target_path=target_path).run()
        expected_paths = ['bin/pip', 'bin/python']
        assert_has_paths(self, expected_paths, target_path)

    def test_pythonpath(self):
        """
        ``InstallVirtualEnv.run`` installs a virtual python whose path does not
        include the system python libraries.
        """
        target_path = FilePath(self.mktemp())
        InstallVirtualEnv(target_path=target_path).run()
        output = check_output([
            target_path.descendant(['bin', 'python']).path,
            '-c', r'import sys; sys.stdout.write("\n".join(sys.path))'
        ])
        self.assertNotIn(
            '/usr/lib/python2.7/site-packages', output.splitlines())

    def test_internal_symlinks_only(self):
        """
        The resulting ``virtualenv`` only contains symlinks to files inside the
        virtualenv and to /usr on the host OS.
        """
        target_path = FilePath(self.mktemp())
        InstallVirtualEnv(target_path=target_path).run()
        allowed_targets = (target_path, FilePath('/usr'),)
        bad_links = []
        for path in target_path.walk():
            if path.islink():
                realpath = path.realpath()
                for allowed_target in allowed_targets:
                    try:
                        realpath.segmentsFrom(allowed_target)
                    except ValueError:
                        pass
                    else:
                        # The target is a descendent of an allowed_target stop
                        # looking and don't attempt to remove it.
                        break
                else:
                    bad_links.append(path)
        if bad_links:
            self.fail(
                '\n'.join(
                    '/'.join(
                        path.segmentsFrom(target_path)
                    ) + ' -> ' + path.realpath().path
                    for path in bad_links
                )
            )


class InstallApplicationTests(TestCase):
    """
    Tests for ``InstallApplication``.
    """
    def test_run(self):
        """
        ``InstallApplication.run`` installs the supplied application in the
        ``target_path``.
        """
        expected_package_uri = '/foo/bar'
        fake_env = fake_virtual_env(self)
        InstallApplication(
            virtualenv_path=fake_env.path,
            package_uri=expected_package_uri
        ).run()
        expected_pip_args = ['--quiet', 'install', expected_package_uri]
        fake_env.assert_pip_args(expected_pip_args)


class CreateLinksTests(TestCase):
    """
    Tests for ``CreateLinks``.
    """
    def test_run(self):
        """
        ``CreateLinks.run`` generates symlinks in ``destination_path`` for all
        the files in ``source_path`` that match ``pattern``. The link targets
        are absolute paths relative to the ``prefix``.
        """
        root = FilePath(self.mktemp())
        flocker_bin = root.descendant(['opt', 'flocker', 'bin'])
        flocker_bin.makedirs()
        flocker_scripts = ('flocker-one', 'flocker-two')
        foreign_scripts = ('foo-one', 'bar-one')
        for script in flocker_scripts + foreign_scripts:
            flocker_bin.child(script).setContent('A script called ' + script)

        system_bin = root.descendant(['usr', 'bin'])
        system_bin.makedirs()

        CreateLinks(
            prefix=root,
            source_path=flocker_bin,
            pattern='flocker-*',
            destination_path=system_bin
        ).run()

        self.assertEqual(
            [FilePath('/opt/flocker/bin').child(script)
             for script in flocker_scripts],
            [child.realpath() for child in system_bin.children()]
        )


class PackageInfo(namedtuple('PackageInfo', 'root name version')):
    """
    :ivar FilePath root: The path to the directory containing the package.
    :ivar bytes name: The name of the package.
    :ivar bytes version: The version of the package.
    """


def canned_package(test_case):
    """
    Create a directory containing an empty Python package which can be
    installed and with a name and version which can later be tested.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :return: A ``PackageInfo`` instance.
    """
    version = '1.2.3'
    name = 'FooBar'

    root = FilePath(test_case.mktemp())
    root.makedirs()
    setup_py = root.child('setup.py')
    setup_py.setContent(
        dedent("""
        import os
        from setuptools import setup, find_packages

        setup(
            name="{package_name}",
            version="{package_version}",
        )
        """).format(package_name=name, package_version=version)
    )

    return PackageInfo(root, name, version)


class GetPackageVersionTests(TestCase):
    """
    Tests for ``GetPackageVersion``.
    """
    def test_version_default(self):
        """
        ``GetPackageVersion.version`` is ``None`` by default.
        """
        step = GetPackageVersion(virtualenv_path=None, package_name=None)
        self.assertIs(None, step.version)

    def test_version_found(self):
        """
        ``GetPackageVersion`` assigns the version of a found package to its
        ``version`` attribute.
        """
        test_env = FilePath(self.mktemp())
        InstallVirtualEnv(target_path=test_env).run()

        test_package = canned_package(self)
        InstallApplication(
            virtualenv_path=test_env, package_uri=test_package.root.path).run()

        step = GetPackageVersion(
            virtualenv_path=test_env, package_name=test_package.name)
        step.run()
        self.assertEqual(test_package.version, step.version)

    def test_version_not_found(self):
        """
        ``GetPackageVersion.run`` leaves the ``version`` attribute set to
        ``None`` if the supplied ``package_name`` is not installed in the
        supplied ``virtual_env``.
        """
        test_env = FilePath(self.mktemp())
        InstallVirtualEnv(target_path=test_env).run()

        step = GetPackageVersion(
            virtualenv_path=test_env,
            package_name='PackageWhichIsNotInstalled'
        )
        step.run()
        self.assertIs(None, step.version)


class BuildPackageTests(TestCase):
    """
    Tests for `BuildPackage`.
    """
    @require_fpm
    def setUp(self):
        pass

    @require_rpm
    def test_rpm(self):
        """
        ``BuildPackage.run`` creates an RPM from the supplied ``source_path``.
        """
        destination_path = FilePath(self.mktemp())
        destination_path.makedirs()
        source_path = FilePath(self.mktemp())
        source_path.makedirs()
        source_path.child('Foo').touch()
        source_path.child('Bar').touch()
        expected_name = 'FooBar'
        expected_prefix = FilePath('/foo/bar')
        expected_epoch = b'3'
        expected_rpm_version = rpm_version('0.3', '0.dev.1')
        expected_license = 'My Test License'
        expected_url = 'https://www.example.com/foo/bar'
        expected_vendor = 'Acme Corporation'
        expected_maintainer = 'noreply@example.com'
        expected_architecture = 'i386'
        expected_description = 'Explosive Tennis Balls'
        BuildPackage(
            package_type="rpm",
            destination_path=destination_path,
            source_path=source_path,
            name=expected_name,
            prefix=expected_prefix,
            epoch=expected_epoch,
            rpm_version=expected_rpm_version,
            license=expected_license,
            url=expected_url,
            vendor=expected_vendor,
            maintainer=expected_maintainer,
            architecture=expected_architecture,
            description=expected_description,
        ).run()
        rpms = glob('{}*.rpm'.format(
            destination_path.child(expected_name).path))
        self.assertEqual(1, len(rpms))

        expected_headers = dict(
            Name=expected_name,
            Epoch=expected_epoch,
            Version=expected_rpm_version.version,
            Release=expected_rpm_version.release,
            License=expected_license,
            URL=expected_url,
            Relocations=expected_prefix.path,
            Vendor=expected_vendor,
            Packager=expected_maintainer,
            Architecture=expected_architecture,
        )
        assert_rpm_headers(self, expected_headers, FilePath(rpms[0]))


    @require_deb
    def test_deb(self):
        """
        ``BuildPackage.run`` creates a .deb package from the supplied
        ``source_path``.
        """
        destination_path = FilePath(self.mktemp())
        destination_path.makedirs()
        source_path = FilePath(self.mktemp())
        source_path.makedirs()
        source_path.child('Foo').touch()
        source_path.child('Bar').touch()
        expected_name = 'FooBar'.lower()
        expected_prefix = FilePath('/foo/bar')
        expected_epoch = b'3'
        expected_rpm_version = rpm_version('0.3', '0.dev.1')
        expected_license = 'My Test License'
        expected_url = 'https://www.example.com/foo/bar'
        expected_vendor = 'Acme Corporation'
        expected_maintainer = 'noreply@example.com'
        expected_architecture = 'i386'
        expected_description = 'Explosive Tennis Balls'
        BuildPackage(
            package_type="deb",
            destination_path=destination_path,
            source_path=source_path,
            name=expected_name,
            prefix=expected_prefix,
            epoch=expected_epoch,
            rpm_version=expected_rpm_version,
            license=expected_license,
            url=expected_url,
            vendor=expected_vendor,
            maintainer=expected_maintainer,
            architecture=expected_architecture,
            description=expected_description,
        ).run()
        packages = glob('{}*.deb'.format(
            destination_path.child(expected_name.lower()).path))
        self.assertEqual(1, len(packages))

        expected_headers = dict(
            Package=expected_name,
            Version=(
                expected_epoch
                + b':'
                + expected_rpm_version.version
                + '-'
                + expected_rpm_version.release
            ),
            License=expected_license,
            Vendor=expected_vendor,
            Architecture=expected_architecture,
            Maintainer=expected_maintainer,
            Homepage=expected_url,
        )
        assert_deb_headers(self, expected_headers, FilePath(packages[0]))


class SumoPackageBuilderTests(TestCase):
    """
    Tests for ``sumo_package_builder``.
    """
    def test_steps(self):
        """
        A sequence of build steps is returned.
        """
        expected_package_type = 'rpm'
        expected_destination_path = FilePath(self.mktemp())
        expected_target_path = FilePath(self.mktemp())
        expected_virtualenv_path = expected_target_path.descendant(['opt', 'flocker'])
        expected_sysbin_path = expected_target_path.descendant(['usr', 'bin'])
        expected_name = 'Flocker'
        expected_prefix = FilePath('/')
        expected_epoch = b'0'
        expected_package_uri = '/foo/bar'
        expected_package_version_step = GetPackageVersion(
            virtualenv_path=expected_virtualenv_path,
            package_name=expected_name
        )
        expected_version = DelayedRpmVersion(
            package_version_step=expected_package_version_step
        )
        expected_license = 'ASL 2.0'
        expected_url = 'https://clusterhq.com'
        expected_vendor = 'ClusterHQ'
        expected_maintainer = 'noreply@build.clusterhq.com'
        expected_architecture = 'native'
        expected_description = (
            'A Docker orchestration and volume management tool')

        expected = BuildSequence(
            steps=(
                InstallVirtualEnv(target_path=expected_virtualenv_path),
                InstallApplication(virtualenv_path=expected_virtualenv_path,
                                   package_uri=expected_package_uri),
                expected_package_version_step,
                CreateLinks(
                    prefix=expected_target_path,
                    source_path=expected_virtualenv_path.child('bin'),
                    pattern='flocker-*',
                    destination_path=expected_sysbin_path,
                ),
                BuildPackage(
                    package_type=expected_package_type,
                    destination_path=expected_destination_path,
                    source_path=expected_target_path,
                    name=expected_name,
                    prefix=expected_prefix,
                    epoch=expected_epoch,
                    rpm_version=expected_version,
                    license=expected_license,
                    url=expected_url,
                    vendor=expected_vendor,
                    maintainer=expected_maintainer,
                    architecture=expected_architecture,
                    description=expected_description,
                )
            )
        )
        assert_equal_steps(
            self,
            expected,
            sumo_package_builder(expected_package_type,
                                 expected_destination_path,
                                 expected_package_uri,
                                 target_dir=expected_target_path))


    @require_fpm
    @require_rpm
    def test_functional_rpm(self):
        """
        An RPM file with the expected headers is built.
        """
        destination_path = FilePath(self.mktemp())
        destination_path.makedirs()
        expected_name = 'Flocker'
        expected_python_version = check_output(
            ['python', 'setup.py', '--version'], cwd=FLOCKER_PATH.path).strip()
        expected_rpm_version = make_rpm_version(expected_python_version)

        sumo_package_builder('rpm', destination_path, FLOCKER_PATH.path).run()

        rpms = glob('{}*.rpm'.format(
            destination_path.child(expected_name).path))
        self.assertEqual(1, len(rpms))

        expected_headers = dict(
            Name=expected_name,
            Epoch=b'0',
            Version=expected_rpm_version.version,
            Release=expected_rpm_version.release,
            License='ASL 2.0',
            URL='https://clusterhq.com',
            Relocations=b'/',
            Vendor='ClusterHQ',
            Packager='noreply@build.clusterhq.com',
            Architecture='x86_64',
            Description='A Docker orchestration and volume management tool',
        )
        rpm_file = FilePath(rpms[0])
        assert_rpm_headers(self, expected_headers, rpm_file)
        assert_rpm_requires(self, FLOCKER_DEPENDENCIES_RPM, rpm_file)
        assert_rpm_lint(self, rpm_file)

    @require_fpm
    @require_deb
    def test_functional_deb(self):
        """
        An deb file with the expected headers is built.
        """
        destination_path = FilePath(self.mktemp())
        destination_path.makedirs()
        expected_name = 'Flocker'.lower()
        expected_python_version = check_output(
            ['python', 'setup.py', '--version'], cwd=FLOCKER_PATH.path).strip()
        expected_rpm_version = make_rpm_version(expected_python_version)

        sumo_package_builder('deb', destination_path, FLOCKER_PATH.path).run()

        packages = glob('{}*.deb'.format(
            destination_path.child(expected_name).path))
        self.assertEqual(1, len(packages))

        expected_headers = dict(
            Package=expected_name,
            Version=(
                b'0:'
                + expected_rpm_version.version
                + '-' +
                expected_rpm_version.release
            ),
            License='ASL 2.0',
            Homepage='https://clusterhq.com',
            Vendor='ClusterHQ',
            Maintainer='noreply@build.clusterhq.com',
            Architecture='amd64',
            Description='A Docker orchestration and volume management tool',
            Depends=', '.join(FLOCKER_DEPENDENCIES_DEB)
        )
        package_file = FilePath(packages[0])
        assert_deb_headers(self, expected_headers, package_file)
        assert_deb_lint(self, package_file)


# XXX: These warnings are being ignored but should probably be fixed.
RPMLINT_IGNORED_WARNINGS = (
    'dir-or-file-in-opt',
    'non-standard-executable-perm',
    'incorrect-fsf-address',
    'pem-certificate',
    'non-executable-script',
    'devel-file-in-non-devel-package',
    'dangling-relative-symlink',
    'dangling-symlink',
    'no-documentation',
    'no-changelogname-tag',
    'non-standard-group',
    'backup-file-in-package',
    'no-manual-page-for-binary',
    'unstripped-binary-or-object',
    'zero-length',
    # Only on Centos7 (not Fedora)
    # See http://fedoraproject.org/wiki/Common_Rpmlint_issues#no-binary
    'no-binary',
    'python-bytecode-without-source',
)


def assert_rpm_lint(test_case, rpm_path):
    """
    Fail for certain rpmlint warnings on a supplied RPM file.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :param FilePath rpm_path: The path to the RPM file to check.
    """
    try:
        check_output(['rpmlint', rpm_path.path])
    except CalledProcessError as e:
        output = []
        for line in e.output.splitlines():
            # Ignore certain warning lines
            show_line = True
            for ignored in RPMLINT_IGNORED_WARNINGS:
                if ignored in line:
                    show_line = False
                    break
            if show_line:
                output.append(line)

        # Don't print out the summary line unless there are some unfiltered
        # warnings.
        if len(output) > 1:
            test_case.fail('rpmlint warnings:\n{}'.format('\n'.join(output)))


# See https://www.debian.org/doc/manuals/developers-reference/tools.html#lintian
LINTIAN_IGNORED_WARNINGS = (
    'script-not-executable',
    'binary-without-manpage',
    'dir-or-file-in-opt',
    'unstripped-binary-or-object',
    'missing-dependency-on-libc',
    'no-copyright-file',
    'description-synopsis-starts-with-article',
    'extended-description-is-empty',
    'debian-revision-not-well-formed',
    'maintainer-name-missing',
    'unknown-section',
    'non-standard-file-perm',
    'extra-license-file',
    'non-standard-executable-perm',
)


def assert_deb_lint(test_case, package_path):
    """
    Fail for certain lintian warnings on a supplied ``package_path``.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :param FilePath package_path: The path to the deb file to check.
    """
    try:
        check_output(['lintian', package_path.path])
    except CalledProcessError as e:
        output = []
        for line in e.output.splitlines():
            # Ignore certain warning lines
            show_line = True
            for ignored in LINTIAN_IGNORED_WARNINGS:
                if ignored in line:
                    show_line = False
                    break
            if show_line:
                output.append(line)

        # Don't print out the summary line unless there are some unfiltered
        # warnings.
        if len(output) > 1:
            test_case.fail('lintian warnings:\n{}'.format('\n'.join(output)))


class BuildOptionsTests(TestCase):
    """
    Tests for ``BuildOptions``.
    """

    def test_defaults(self):
        """
        ``BuildOptions`` destination path defaults to the current working
        directory.
        """
        expected_defaults = {
            'destination-path': '.',
            'package-type': 'native',
        }
        self.assertEqual(expected_defaults, BuildOptions())

    def test_native(self):
        """
        ``BuildOptions`` package-type is selected automatically if the keyword
        ``native`` is supplied.
        """
        options = BuildOptions()
        options.parseOptions(
            ['--package-type=native', 'http://example.com/fake/uri'])
        self.assertEqual(_native_package_type(), options['package-type'])

    def test_package_uri_missing(self):
        """
        ``BuildOptions`` requires a single positional argument containing the
        URI of the Python package which is being packaged.
        """
        exception = self.assertRaises(
            UsageError, BuildOptions().parseOptions, [])
        self.assertEqual('Wrong number of arguments.', str(exception))

    def test_package_uri_supplied(self):
        """
        ``BuildOptions`` saves the supplied ``package-uri``.
        """
        expected_uri = 'http://www.example.com/foo-bar.whl'

        options = BuildOptions()
        options.parseOptions([expected_uri])

        self.assertEqual(expected_uri, options['package-uri'])


class BuildScriptTests(TestCase):
    """
    Tests for ``BuildScript``.
    """
    def test_usage_error_status(self):
        """
        ``BuildScript.main`` raises ``SystemExit`` if there are missing command
        line options.
        """
        fake_sys_module = FakeSysModule(argv=[])
        script = BuildScript(sys_module=fake_sys_module)
        exception = self.assertRaises(SystemExit, script.main)
        self.assertEqual(1, exception.code)

    def test_usage_error_message(self):
        """
        ``BuildScript.main`` prints a usage error to ``stderr`` if there are
        missing command line options.
        """
        fake_sys_module = FakeSysModule(argv=[])
        script = BuildScript(sys_module=fake_sys_module)
        try:
            script.main()
        except SystemExit:
            pass
        self.assertEqual(
            'Wrong number of arguments.',
            fake_sys_module.stderr.getvalue().splitlines()[-1]
        )

    def test_build_command(self):
        """
        ``BuildScript.build_command`` is ``sumo_package_builder`` by default.
        """
        self.assertIs(sumo_package_builder, BuildScript.build_command)

    def test_run(self):
        """
        ``BuildScript.main`` calls ``run`` on the instance returned by
        ``build_command``.
        """
        expected_destination_path = FilePath(self.mktemp())
        expected_package_uri = 'http://www.example.com/foo/bar.whl'
        fake_sys_module = FakeSysModule(
            argv=[
                'build-command-name',
                '--destination-path=%s' % (expected_destination_path.path,),
                '--package-type=native',
                expected_package_uri]
        )
        script = BuildScript(sys_module=fake_sys_module)
        build_step = SpyStep()
        arguments = []
        def record_arguments(*args, **kwargs):
            arguments.append((args, kwargs))
            return build_step
        script.build_command = record_arguments
        script.main()
        expected_build_arguments = [(
            (),
            dict(destination_path=expected_destination_path,
                 package_uri=expected_package_uri,
                 package_type=_native_package_type())
        )]
        self.assertEqual(expected_build_arguments, arguments)
        self.assertTrue(build_step.ran)
