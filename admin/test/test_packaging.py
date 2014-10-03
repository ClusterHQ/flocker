# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.packaging``.
"""
from glob import glob
from subprocess import check_output

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from ..packaging import (
    sumo_rpm_builder, InstallVirtualEnv, InstallApplication, BuildRpm,
    BuildSequence
)
from ..release import make_rpm_version, rpm_version

FLOCKER_PATH = FilePath(__file__).parent().parent().parent()


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


class InstallApplicationTests(TestCase):
    """
    Tests for `InstallApplication`.
    """
    def test_run(self):
        """
        `InstallApplication.run` installs the supplied application in the
        `target_path`.
        """
        expected_package_path = FilePath('/foo/bar')
        fake_env = fake_virtual_env(self)
        InstallApplication(
            virtualenv_path=fake_env.path,
            package_path=expected_package_path
        ).run()
        expected_pip_args = ['--quiet', 'install', expected_package_path.path]
        fake_env.assert_pip_args(expected_pip_args)


class BuildRpmTests(TestCase):
    """
    Tests for `BuildRpm`.
    """
    def test_run(self):
        """
        `BuildRpm.run` creates an RPM from the supplied `source_path`.
        """
        source_path = FilePath(self.mktemp())
        source_path.makedirs()
        expected_name = 'FooBar'
        expected_rpm_version = rpm_version('0.3', '0.dev.1')
        expected_license = 'My Test License'
        expected_url = 'https://www.example.com/foo/bar'
        BuildRpm(
            source_path=source_path, 
            name=expected_name,
            rpm_version=expected_rpm_version,
            license=expected_license,
            url=expected_url,
        ).run()
        rpms = glob('{}*.rpm'.format(expected_name))
        self.assertEqual(1, len(rpms))
        expected_headers = dict(
            Name=expected_name,
            Version=expected_rpm_version.version,
            Release=expected_rpm_version.release,
            License=expected_license,
            URL=expected_url,
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
        expected_target_path = self.mktemp()
        expected_name = 'Flocker'
        expected_package_path = '/foo/bar'
        expected_version = '0.3dev1'
        expected_license = 'ASL 2.0'
        expected_url = 'https://clusterhq.com'
        expected = BuildSequence(
            steps=(
                InstallVirtualEnv(target_path=expected_target_path),
                InstallApplication(virtualenv_path=expected_target_path,
                                   package_path=expected_package_path),
                BuildRpm(source_path=expected_target_path,
                         name=expected_name,
                         rpm_version=make_rpm_version(expected_version),
                         license=expected_license,
                         url=expected_url,)
            )
        )
        self.assertEqual(
            expected,
            sumo_rpm_builder(expected_package_path,
                             expected_version,
                             target_dir=expected_target_path))

    def test_functional(self):
        """
        An RPM file with the expected headers is built.
        """
        expected_name = 'Flocker'
        expected_python_version = check_output(
            ['python', 'setup.py', '--version'], cwd=FLOCKER_PATH.path).strip()
        expected_rpm_version = make_rpm_version(expected_python_version)
        sumo_rpm_builder(FLOCKER_PATH, expected_python_version).run()
        rpms = glob('{}*.rpm'.format(expected_name))
        self.assertEqual(1, len(rpms))
        expected_headers = dict(
            Name=expected_name,
            Version=expected_rpm_version.version,
            Release=expected_rpm_version.release,
            License='ASL 2.0',
            URL='https://clusterhq.com',
        )
        assert_rpm_headers(self, expected_headers, rpms[0])
