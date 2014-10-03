# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.common._release``.
"""

from twisted.trial.unittest import TestCase

from ..release import rpm_version, make_rpm_version


class MakeRpmVersionTests(TestCase):
    """
    Tests for ``make_rpm_version``.
    """
    def test_good(self):
        """
        ``make_rpm_version`` gives the expected ``rpm_version`` instances when
        supplied with valid ``flocker_version_number``s.
        """
        expected = {
            '0.1.0': rpm_version('0.1.0', '1'),
            '0.1.0-99-g3d644b1': rpm_version('0.1.0', '1.99.g3d644b1'),
            '0.1.1pre1': rpm_version('0.1.1', '0.pre.1'),
            '0.1.1': rpm_version('0.1.1', '1'),
            '0.2.0dev1': rpm_version('0.2.0', '0.dev.1'),
            '0.2.0dev2-99-g3d644b1': rpm_version('0.2.0', '0.dev.2.99.g3d644b1'),
            '0.2.0dev3-100-g3d644b2-dirty': rpm_version(
                '0.2.0', '0.dev.3.100.g3d644b2.dirty'),
        }
        unexpected_results = []
        for supplied_version, expected_rpm_version in expected.items():
            actual_rpm_version = make_rpm_version(supplied_version)
            if actual_rpm_version != expected_rpm_version:
                unexpected_results.append((
                    supplied_version,
                    actual_rpm_version,
                    expected_rpm_version
                ))

        if unexpected_results:
            self.fail(unexpected_results)

    def test_non_integer_suffix(self):
        """
        ``make_rpm_version`` raises ``Exception`` when supplied with a version
        with a non-integer pre or dev suffix number.
        """
        exception = self.assertRaises(Exception, make_rpm_version, '0.1.2preX')

        self.assertEqual(
            u'Non-integer value "X" for "pre". Supplied version 0.1.2preX',
            unicode(exception)
        )


from subprocess import check_output
from twisted.python.filepath import FilePath
from ..release import sumo_rpm_builder, InstallVirtualEnv, InstallApplication, BuildRpm, BuildSequence

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
            '{}Missing items: {}, Mismatch items:  {}'.format(
                message, missing_items, mismatch_items)
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
    # unzip a prepared virtual env from a tgz
    # OR
    # maybe build a virtual env if a cached archive isn't found and zip it up for future use before returning yielding the path
    # check_call('tar --directory {} xf {}'.format(target_dir, virtual_env_archive).split())
    # return target_dir
    pass


FLOCKER_PATH = FilePath(__file__).parent().parent().parent().path
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
        # extract a canned virtual env
        # virtual_env = canned_virtual_env()
        sumo_rpm_builder(FLOCKER_PATH).run()
        from glob import glob
        rpms = glob('*.rpm')
        self.assertEqual(1, len(rpms))
        expected_headers = dict(
            version='foo',
            release='bar'
        )
        assertRpmHeaders(self, expected_headers, rpms[0])
