# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.packaging``.
"""
from glob import glob
from subprocess import check_output
from unittest import skipIf

from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.python.usage import UsageError
from twisted.trial.unittest import TestCase

from ..packaging import (
    sumo_rpm_builder, InstallVirtualEnv, InstallApplication, BuildRpm,
    BuildSequence, BuildOptions,
)
from ..release import make_rpm_version, rpm_version

FLOCKER_PATH = FilePath(__file__).parent().parent().parent()

# XXX: Get fpm installed on the build slaves.
# See https://github.com/ClusterHQ/build.clusterhq.com/issues/32
require_fpm = skipIf(not which('fpm'), "Tests require the `fpm` command.")


def assert_equal_steps(test_case, expected, actual):
    """
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



def assert_dict_contains(test_case, expected_dict, actual_dict, message=''):
    """
    `actual_dict` contains all the items in `expected_dict`.
    """
    missing_items = []
    mismatch_items = []
    no_value = object()
    for key, expected_value in expected_dict.items():
        actual_value = actual_dict.get(key, no_value)
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
                message, missing_items, mismatch_items, actual_dict)
        )


def assert_rpm_headers(test_case, expected_headers, rpm_path):
    """
    The `RPM` file at `rpm_path` contains all the `expected_headers`.
    """
    output = check_output(['rpm', '--query', '--info', '--package', rpm_path])
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


def fake_virtual_env(test_case):
    """
    Create a directory containing a fake pip executable which records its
    arguments when executed.

    Return an object containing methods with which to make assertions about the
    fake virtualenv.
    """
    virtualenv_path = FilePath(test_case.mktemp())
    pip_log_path = virtualenv_path.child('pip.log')
    from textwrap import dedent
    bin_path = virtualenv_path.child('bin')
    bin_path.makedirs()
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
    A `BuildStep` which records the fact that it has been run.
    """
    ran = False

    def run(self):
        self.ran = True


class BuildSequenceTests(TestCase):
    """
    Tests for `BuildSequence`.
    """
    def test_run(self):
        """
        `BuildSequence` calls the `run` method of each of its `steps`.
        """
        step1 = SpyStep()
        step2 = SpyStep()

        BuildSequence(steps=(step1, step2)).run()

        self.assertEqual((True, True), (step1.ran, step2.ran))


def assert_has_paths(test_case, expected_paths, parent_path):
    """
    Fail if any of the `expected_paths` are not existing relative paths of
    `parent_path`.
    """
    missing_paths = []
    for path in expected_paths:
        if not parent_path.preauthChild(path).exists():
            missing_paths.append(path)
        if missing_paths:
            test_case.fail('Missing paths: {}'.format(missing_paths))


class InstallVirtualEnvTests(TestCase):
    """
    Tests for `InstallVirtualEnv`.
    """
    def test_run(self):
        """
        `InstallVirtualEnv.run` installs a virtual python environment in its
        `target_path`.
        """
        target_path = FilePath(self.mktemp())
        InstallVirtualEnv(target_path=target_path).run()
        expected_paths = ['bin/pip', 'bin/python']
        assert_has_paths(self, expected_paths, target_path)

    def test_internal_symlinks_only(self):
        """
        The resulting `virtualenv` only contains symlinks to files in /lib.
        """
        target_path = FilePath(self.mktemp())
        InstallVirtualEnv(target_path=target_path).run()
        allowed_targets = (target_path, FilePath('/usr'),)
        bad_links = []
        for path in target_path.walk():
            # if path.path.endswith('lib64/python2.7/ntpath.py'):
            #     import pdb; pdb.set_trace()
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
                    '/'.join(path.segmentsFrom(target_path)) + ' -> ' + path.realpath().path
                    for path in bad_links
                )
            )

class InstallApplicationTests(TestCase):
    """
    Tests for `InstallApplication`.
    """
    def test_run(self):
        """
        `InstallApplication.run` installs the supplied application in the
        `target_path`.
        """
        expected_package_uri = '/foo/bar'
        fake_env = fake_virtual_env(self)
        InstallApplication(
            virtualenv_path=fake_env.path,
            package_uri=expected_package_uri
        ).run()
        expected_pip_args = ['--quiet', 'install', expected_package_uri]
        fake_env.assert_pip_args(expected_pip_args)


class BuildRpmTests(TestCase):
    """
    Tests for `BuildRpm`.
    """
    @require_fpm
    def setUp(self):
        pass

    def test_run(self):
        """
        `BuildRpm.run` creates an RPM from the supplied `source_path`.
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
        BuildRpm(
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
        assert_rpm_headers(self, expected_headers, rpms[0])


class SumoRpmBuilderTests(TestCase):
    """
    Tests for `sumo_rpm_builder`.
    """
    def test_steps(self):
        """
        A sequence of build steps is returned.
        """
        expected_destination_path = FilePath(self.mktemp())
        expected_target_path = FilePath(self.mktemp())
        expected_name = 'Flocker'
        expected_prefix = FilePath('/opt/flocker')
        expected_epoch = b'0'
        expected_package_uri = '/foo/bar'
        expected_version = '0.3dev1'
        expected_license = 'ASL 2.0'
        expected_url = 'https://clusterhq.com'
        expected_vendor = 'ClusterHQ'
        expected_maintainer = 'noreply@build.clusterhq.com'
        expected_architecture = None
        expected_description = 'A Docker orchestration and volume management tool'

        expected = BuildSequence(
            steps=(
                InstallVirtualEnv(target_path=expected_target_path),
                InstallApplication(virtualenv_path=expected_target_path,
                                   package_uri=expected_package_uri),
                BuildRpm(
                    destination_path=expected_destination_path,
                    source_path=expected_target_path,
                    name=expected_name,
                    prefix=expected_prefix,
                    epoch=expected_epoch,
                    rpm_version=make_rpm_version(expected_version),
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
            sumo_rpm_builder(expected_destination_path,
                             expected_package_uri,
                             expected_version,
                             target_dir=expected_target_path))

    @require_fpm
    def test_functional(self):
        """
        An RPM file with the expected headers is built.
        """
        destination_path = FilePath(self.mktemp())
        destination_path.makedirs()
        expected_name = 'Flocker'
        expected_python_version = check_output(
            ['python', 'setup.py', '--version'], cwd=FLOCKER_PATH.path).strip()
        expected_rpm_version = make_rpm_version(expected_python_version)
        sumo_rpm_builder(
            destination_path, FLOCKER_PATH.path, expected_python_version).run()
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
            Relocations=b'/opt/flocker',
            Vendor='ClusterHQ',
            Packager='noreply@build.clusterhq.com',
            Architecture='noarch',
            Description='A Docker orchestration and volume management tool',
        )
        assert_rpm_headers(self, expected_headers, rpms[0])
        assert_rpmlint(self, rpms[0])

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
    'arch-independent-package-contains-binary-or-object',
    'no-changelogname-tag',
    'non-standard-group',
    'backup-file-in-package',
)

def assert_rpmlint(test_case, rpm_path):
    """
    Fail for certain rpmlint warnings on a supplied RPM file.
    """
    from subprocess import check_output, CalledProcessError
    try:
        check_output(['rpmlint', rpm_path])
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

        # Don't print out the summary line unless there are some unfiltered warnings.
        if len(output) > 1:
            test_case.fail('rpmlint warnings:\n{}'.format('\n'.join(output)))


class BuildOptionsTests(TestCase):
    """
    Tests for ``admin.packaging.BuildOptions``.
    """

    def test_defaults(self):
        """
        ``BuildOptions`` default destination and package path default to the
        current working directory.
        """
        expected_defaults = {
            'destination-path': '.',
        }
        self.assertEqual(expected_defaults, BuildOptions())

    def test_package_uri_missing(self):
        """
        ``BuildOptions`` requires a single positional argument describing the
        location of the Python package which is being packaged.
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
