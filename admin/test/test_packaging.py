# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.packaging``.
"""
from glob import glob
from subprocess import check_output, check_call

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from ..packaging import (
    sumo_rpm_builder, InstallVirtualEnv, InstallApplication, BuildRpm,
    BuildSequence
)
from ..release import make_rpm_version

FLOCKER_PATH = FilePath(__file__).parent().parent().parent().path


def assertDictContains(test_case, expected_dict, actual_dict, message=''):
    """
    `actual_dict` contains all the items in `expected_dict`
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


def assertRpmHeaders(test_case, expected_headers, rpm_path):
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

    assertDictContains(
        test_case, expected_headers, actual_headers, 'Missing RPM Headers: ')


def canned_virtual_env(virtualenv_archive, target_dir):
    """
    """
    # unzip a prepared virtual env from a tgz
    # OR
    # maybe build a virtual env if a cached archive isn't found and zip it up
    # for future use before returning yielding the path
    # check_call([
    #     'tar',
    #     '--directory', target_dir,
    #     '--extract',
    #     '--file', virtualenv_archive
    # ])
    pass


class SpyStep(object):
    """
    """
    ran = False
    def run(self):
        """
        """
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
        virtualenv_path = FilePath(self.mktemp())
        pip_log_path = virtualenv_path.child('pip.log')
        from textwrap import dedent
        bin_path = virtualenv_path.child('bin')
        bin_path.makedirs()
        pip_path = bin_path.child('pip')
        pip_path.setContent(
            dedent("""
            #!/usr/bin/env python
            import sys
            open({pip_log_path}, 'w').write(' '.join(sys.argv[1:]))
            """).lstrip().format(pip_log_path=repr(pip_log_path.path))
        )
        pip_path.chmod(0700)
        InstallApplication(
            virtualenv_path=virtualenv_path,
            package_path=expected_package_path
        ).run()
        expected_pip_args = 'install {}'.format(expected_package_path.path)
        self.assertEqual(expected_pip_args, pip_log_path.getContent().strip())


class SumoRpmBuilderTests(TestCase):
    """
    Tests for `sumo_rpm_builder`.
    """
    def test_steps(self):
        """
        A sequence of build steps is returned.
        """
        expected_target_path = self.mktemp()
        expected_package_path = '/foo/bar'
        expected = BuildSequence(
            steps=(
                InstallVirtualEnv(target_path=expected_target_path),
                InstallApplication(virtualenv_path=expected_target_path,
                                   package_path=expected_package_path),
                BuildRpm(source_path=expected_target_path)
            )
        )
        self.assertEqual(
            expected,
            sumo_rpm_builder(expected_package_path,
                             target_dir=expected_target_path))

    def test_functional(self):
        """
        An RPM file with the expected headers is built.
        """
        expected_python_version = check_output(
            ['python', 'setup.py', '--version'], cwd=FLOCKER_PATH).strip()
        expected_rpm_version = make_rpm_version(expected_python_version)
        sumo_rpm_builder(FLOCKER_PATH).run()
        rpms = glob('*.rpm')
        self.assertEqual(1, len(rpms))
        expected_headers = dict(
            Name='Flocker',
            Version=expected_rpm_version.version,
            Release=expected_rpm_version.release,
            License='Apache',
            URL='http://clusterhq.com',
            Vendor='ClusterHQ',
        )
        assertRpmHeaders(self, expected_headers, rpms[0])
