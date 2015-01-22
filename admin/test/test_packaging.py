# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.packaging``.
"""

from glob import glob
from subprocess import check_output
from textwrap import dedent
from unittest import skipIf
from StringIO import StringIO

from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.python.usage import UsageError
from twisted.trial.unittest import TestCase

from virtualenv import REQUIRED_MODULES as VIRTUALENV_REQUIRED_MODULES

from flocker.testtools import FakeSysModule

from .. import packaging
from ..packaging import (
    omnibus_package_builder, InstallVirtualEnv, InstallApplication,
    BuildPackage, BuildSequence, BuildOptions, BuildScript, DockerBuildOptions,
    DockerBuildScript, GetPackageVersion, DelayedRpmVersion, CreateLinks,
    PythonPackage, create_virtualenv, VirtualEnv, PackageTypes, Distribution,
    Dependency, build_in_docker, DockerBuild, DockerRun,
    PACKAGE, PACKAGE_PYTHON, PACKAGE_CLI, PACKAGE_NODE,
    make_dependencies,
    LintPackage,
)
from ..release import rpm_version

FLOCKER_PATH = FilePath(__file__).parent().parent().parent()

require_fpm = skipIf(not which('fpm'), "Tests require the ``fpm`` command.")
require_rpm = skipIf(not which('rpm'), "Tests require the ``rpm`` command.")
require_rpmlint = skipIf(not which('rpmlint'),
                         "Tests require the ``rpmlint`` command.")
require_dpkg = skipIf(not which('dpkg'), "Tests require the ``dpkg`` command.")
require_lintian = skipIf(not which('lintian'),
                         "Tests require the ``lintian`` command.")

DOCKER_SOCK = '/var/run/docker.sock'


def assert_equal_steps(test_case, expected, actual):
    """
    Assert that the list of provided steps are the same.
    If they are not, display the differences intelligently.

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
        index = 0
        for index, expected_step in enumerate(expected_steps):
            try:
                actual_step = actual_steps[index]
            except IndexError:
                missing_steps = expected_steps[index:]
                break
            if expected_step != actual_step:
                mismatch_steps.append(
                    '* expected: {} !=\n'
                    '  actual:   {}'.format(
                        expected_step, actual_step))
        extra_steps = actual_steps[index+1:]
        if mismatch_steps or missing_steps or extra_steps:
            test_case.fail(
                'Step Mismatch\n'
                'Mismatch:\n{}\n'
                'Missing:\n{}\n'
                'Extra:\n{}'.format(
                    '\n'.join(mismatch_steps), missing_steps, extra_steps)
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


def parse_colon_dict(data):
    """
    Parse colon seperated values into a dictionary, treating lines
    lacking a colon as continutation lines.

    Any leading lines without a colon will be associated with the key
    ``None``.

    This is the format output by ``rpm --query`` and ``dpkg --info``.

    :param bytes data: Data to parse
    :return: A ``dict`` containing the parsed data.
    """
    result = {}
    key = None
    for line in data.splitlines():
        parts = [value.strip() for value in line.split(':', 1)]
        if len(parts) == 2:
            key, val = parts
            result[key] = val
        else:
            result.setdefault(key, '')
            result[key] += parts[0]
    return result


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
    actual_headers = parse_colon_dict(output)

    assert_dict_contains(
        test_case, expected_headers, actual_headers, 'Missing RPM Headers: '
    )


def assert_rpm_content(test_case, expected_paths, package_path):
    """
    Fail unless the ``RPM`` file at ``rpm_path`` contains all the
    ``expected_paths``.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :param set expected_paths: A set of ``FilePath`` s
    :param FilePath package_path: The path to the package under test.
    """
    output = check_output(
        ['rpm', '--query', '--list', '--package', package_path.path]
    )
    actual_paths = set(map(FilePath, output.splitlines()))
    test_case.assertEqual(expected_paths, actual_paths)


def assert_deb_content(test_case, expected_paths, package_path):
    """
    Fail unless the ``deb`` file at ``package_path`` contains all the
    ``expected_paths``.

    :param test_case: The ``TestCase`` whose assert methods will be called.
    :param set expected_paths: A set of ``FilePath`` s
    :param FilePath package_path: The path to the package under test.
    """
    output_dir = FilePath(test_case.mktemp())
    output_dir.makedirs()
    check_output(['dpkg', '--extract', package_path.path, output_dir.path])

    actual_paths = set()
    for f in output_dir.walk():
        if f.isdir():
            continue
        actual_paths.add(FilePath('/').descendant(f.segmentsFrom(output_dir)))

    test_case.assertEqual(expected_paths, actual_paths)


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
    actual_headers = parse_colon_dict(output)

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


class SpyVirtualEnv(object):
    """
    A ``VirtualEnv`` like class which records the ``package_uri``s which are
    supplied to its ``install`` method.
    """
    def __init__(self):
        self._installed_packages = []

    def install(self, package_uri):
        self._installed_packages.append(package_uri)


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

    :param TestCase test_case: The ``TestCase`` with which to make assertions.
    :param list expected_paths: A ``list`` of ``bytes`` relative path names
        which are expected to exist beneath ``parent_path``.
    :param FilePath parent_path: The root ``FilePath`` in which to search for
        ``expected_paths``.
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
        ``InstallVirtualEnv.run`` installs a virtual python environment using
        create_virtualenv passing ``target_path`` as ``root``.
        """
        virtualenv = VirtualEnv(root=FilePath(self.mktemp()))
        step = InstallVirtualEnv(virtualenv=virtualenv)
        calls = []
        self.patch(
            step, '_create_virtualenv', lambda **kwargs: calls.append(kwargs))
        step.run()
        self.assertEqual([dict(root=virtualenv.root)], calls)


class CreateVirtualenvTests(TestCase):
    """
    """
    def test_bin(self):
        """
        ``create_virtualenv`` installs a virtual python environment in its
        ``target_path``.
        """
        virtualenv = VirtualEnv(root=FilePath(self.mktemp()))
        InstallVirtualEnv(virtualenv=virtualenv).run()
        expected_paths = ['bin/pip', 'bin/python']
        assert_has_paths(self, expected_paths, virtualenv.root)

    def test_pythonpath(self):
        """
        ``create_virtualenv`` installs a virtual python whose path does not
        include the system python libraries.
        """
        target_path = FilePath(self.mktemp())
        create_virtualenv(root=target_path)
        output = check_output([
            target_path.descendant(['bin', 'python']).path,
            '-c', r'import sys; sys.stdout.write("\n".join(sys.path))'
        ])
        # We should probably check for lib64 as well here.
        self.assertNotIn(
            '/usr/lib/python2.7/site-packages', output.splitlines())

    def test_bootstrap_pyc(self):
        """
        ``create_virtualenv`` creates links to the pyc files for all the
        modules required for the virtualenv bootstrap process.
        """
        target_path = FilePath(self.mktemp())
        create_virtualenv(root=target_path)

        py_files = []
        for module_name in VIRTUALENV_REQUIRED_MODULES:
            py_base = target_path.descendant(['lib', 'python2.7', module_name])
            py = py_base.siblingExtension('.py')
            pyc = py_base.siblingExtension('.pyc')
            if py.exists() and False in (py.islink(), pyc.islink()):
                py_files.append('PY: {} > {}\nPYC: {} > {}\n'.format(
                    '/'.join(py.segmentsFrom(target_path)),
                    py.realpath().path,
                    '/'.join(pyc.segmentsFrom(target_path)),
                    pyc.islink() and pyc.realpath().path or 'NOT A SYMLINK'
                ))

        if py_files:
            self.fail(
                'Non-linked bootstrap pyc files in {}: \n{}'.format(
                    target_path, '\n'.join(py_files)
                )
            )

    def test_internal_symlinks_only(self):
        """
        The resulting ``virtualenv`` only contains symlinks to files inside the
        virtualenv and to /usr on the host OS.
        """
        target_path = FilePath(self.mktemp())
        create_virtualenv(root=target_path)
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
                        # The target is a descendent of an allowed_target.
                        break
                else:
                    bad_links.append(path)
        if bad_links:
            self.fail(
                "Symlinks outside of virtualenv detected:" +
                '\n'.join(
                    '/'.join(
                        path.segmentsFrom(target_path)
                    ) + ' -> ' + path.realpath().path
                    for path in bad_links
                )
            )


class VirtualEnvTests(TestCase):
    """
    Tests for ``VirtualEnv``.
    """
    def test_install(self):
        """
        ``VirtualEnv.install`` accepts a ``PythonPackage`` instance and
        installs it.
        """
        virtualenv_dir = FilePath(self.mktemp())
        virtualenv = create_virtualenv(root=virtualenv_dir)
        package_dir = FilePath(self.mktemp())
        package = canned_package(package_dir)
        virtualenv.install(package_dir.path)
        self.assertIn(
            '{}-{}-py2.7.egg-info'.format(package.name, package.version),
            [f.basename() for f in virtualenv_dir.descendant(
                ['lib', 'python2.7', 'site-packages']).children()]
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
        package_uri = 'http://www.example.com/Bar-1.2.3.whl'
        fake_env = SpyVirtualEnv()
        InstallApplication(
            virtualenv=fake_env,
            package_uri=package_uri
        ).run()

        self.assertEqual(
            [package_uri], fake_env._installed_packages)


class CreateLinksTests(TestCase):
    """
    Tests for ``CreateLinks``.
    """
    def test_run(self):
        """
        ``CreateLinks.run`` generates symlinks in ``destination_path`` for all
        the supplied ``links``.
        """
        root = FilePath(self.mktemp())
        bin_dir = root.descendant(['usr', 'bin'])
        bin_dir.makedirs()

        CreateLinks(
            links=frozenset([
                (FilePath('/opt/flocker/bin/flocker-foo'), bin_dir),
                (FilePath('/opt/flocker/bin/flocker-bar'), bin_dir),
            ])
        ).run()

        self.assertEqual(
            set(FilePath('/opt/flocker/bin').child(script)
                for script in ('flocker-foo', 'flocker-bar')),
            set(child.realpath() for child in bin_dir.children())
        )


def canned_package(root):
    """
    Create a directory containing an empty Python package which can be
    installed and with a name and version which can later be tested.

    :param test_case: The ``TestCase`` whose mktemp method will be called.
    :return: A ``PythonPackage`` instance.
    """
    version = '1.2.3'
    name = 'FooBar'
    root.makedirs()
    setup_py = root.child('setup.py')
    setup_py.setContent(
        dedent("""
        from setuptools import setup

        setup(
            name="{package_name}",
            version="{package_version}",
        )
        """).format(package_name=name, package_version=version)
    )

    return PythonPackage(name=name, version=version)


class GetPackageVersionTests(TestCase):
    """
    Tests for ``GetPackageVersion``.
    """
    def test_version_default(self):
        """
        ``GetPackageVersion.version`` is ``None`` by default.
        """
        step = GetPackageVersion(virtualenv=None, package_name=None)
        self.assertIs(None, step.version)

    def test_version_found(self):
        """
        ``GetPackageVersion`` assigns the version of a found package to its
        ``version`` attribute.
        """
        test_env = FilePath(self.mktemp())
        virtualenv = VirtualEnv(root=test_env)
        InstallVirtualEnv(virtualenv=virtualenv).run()
        package_root = FilePath(self.mktemp())
        test_package = canned_package(root=package_root)
        InstallApplication(
            virtualenv=virtualenv, package_uri=package_root.path).run()

        step = GetPackageVersion(
            virtualenv=virtualenv, package_name=test_package.name)
        step.run()
        self.assertEqual(test_package.version, step.version)

    def test_version_not_found(self):
        """
        ``GetPackageVersion.run`` raises an exception if the supplied
        ``package_name`` is not installed in the supplied ``virtual_env``.
        """
        test_env = FilePath(self.mktemp())
        virtualenv = VirtualEnv(root=test_env)
        InstallVirtualEnv(virtualenv=virtualenv).run()

        step = GetPackageVersion(
            virtualenv=virtualenv,
            package_name='PackageWhichIsNotInstalled'
        )
        self.assertRaises(Exception, step.run)


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
        expected_prefix = FilePath('/foo/bar')
        expected_paths = set([
            expected_prefix.child('Foo'),
            expected_prefix.child('Bar'),
            FilePath('/other/file'),
        ])
        expected_name = 'FooBar'
        expected_epoch = b'3'
        expected_rpm_version = rpm_version('0.3', '0.dev.1')
        expected_license = 'My Test License'
        expected_url = 'https://www.example.com/foo/bar'
        expected_vendor = 'Acme Corporation'
        expected_maintainer = 'noreply@example.com'
        expected_architecture = 'i386'
        expected_description = 'Explosive Tennis Balls'
        expected_dependencies = ['test-dep', 'version-dep >= 42']
        BuildPackage(
            package_type=PackageTypes.RPM,
            destination_path=destination_path,
            source_paths={
                source_path: FilePath('/foo/bar'),
                source_path.child('Foo'): FilePath('/other/file'),
            },
            name=expected_name,
            prefix=FilePath('/'),
            epoch=expected_epoch,
            rpm_version=expected_rpm_version,
            license=expected_license,
            url=expected_url,
            vendor=expected_vendor,
            maintainer=expected_maintainer,
            architecture=expected_architecture,
            description=expected_description,
            category="Applications/System",
            dependencies=[
                Dependency(package='test-dep'),
                Dependency(package='version-dep', compare='>=', version='42')],
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
            Vendor=expected_vendor,
            Packager=expected_maintainer,
            Architecture=expected_architecture,
            Group="Applications/System",
        )
        rpm_path = FilePath(rpms[0])
        assert_rpm_requires(self, expected_dependencies, rpm_path)
        assert_rpm_headers(self, expected_headers, rpm_path)
        assert_rpm_content(self, expected_paths, rpm_path)

    @require_dpkg
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
        expected_prefix = FilePath('/foo/bar')
        expected_paths = set([
            expected_prefix.child('Foo'),
            expected_prefix.child('Bar'),
            FilePath('/other/file'),
            # This is added automatically by fpm despite not supplying the
            # --deb-changelog option
            FilePath('/usr/share/doc/foobar/changelog.Debian.gz'),
        ])
        expected_name = 'FooBar'.lower()
        expected_epoch = b'3'
        expected_rpm_version = rpm_version('0.3', '0.dev.1')
        expected_license = 'My Test License'
        expected_url = 'https://www.example.com/foo/bar'
        expected_vendor = 'Acme Corporation'
        expected_maintainer = 'noreply@example.com'
        expected_architecture = 'i386'
        expected_description = 'Explosive Tennis Balls'
        BuildPackage(
            package_type=PackageTypes.DEB,
            destination_path=destination_path,
            source_paths={
                source_path: FilePath('/foo/bar'),
                source_path.child('Foo'): FilePath('/other/file'),
            },
            name=expected_name,
            prefix=FilePath("/"),
            epoch=expected_epoch,
            rpm_version=expected_rpm_version,
            license=expected_license,
            url=expected_url,
            vendor=expected_vendor,
            maintainer=expected_maintainer,
            architecture=expected_architecture,
            description=expected_description,
            category="admin",
            dependencies=[
                Dependency(package='test-dep'),
                Dependency(package='version-dep', compare='>=', version='42')],
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
            Depends=', '.join(['test-dep', 'version-dep (>= 42)']),
            Section="admin",
        )
        assert_deb_headers(self, expected_headers, FilePath(packages[0]))
        assert_deb_content(self, expected_paths, FilePath(packages[0]))


class LintPackageTests(TestCase):
    """
    Tests for ``LintPackage``.
    """

    @require_fpm
    def setUp(self):
        pass

    def assert_lint(self, package_type, expected_output):
        """
        ``LintPackage.run`` reports only unfiltered errors and raises
        ``SystemExit``.

        :param PackageTypes package_type: The type of package to test.
        :param bytes expected_output: The expected output of the linting.
        """
        destination_path = FilePath(self.mktemp())
        destination_path.makedirs()
        source_path = FilePath(self.mktemp())
        source_path.makedirs()
        source_path.child('Foo').touch()
        source_path.child('Bar').touch()
        BuildPackage(
            package_type=package_type,
            destination_path=destination_path,
            source_paths={
                source_path: FilePath('/foo/bar'),
                source_path.child('Foo'): FilePath('/opt/file'),
            },
            name="package-name",
            prefix=FilePath('/'),
            epoch=b'3',
            rpm_version=rpm_version('0.3', '0.dev.1'),
            license="Example",
            url="https://package.example/",
            vendor="Acme Corporation",
            maintainer='Someone <noreply@example.com>',
            architecture="all",
            description="Description\n\nExtended",
            category="none",
            dependencies=[]
        ).run()

        step = LintPackage(
            package_type=package_type,
            destination_path=destination_path,
            epoch=b'3',
            rpm_version=rpm_version('0.3', '0.dev.1'),
            package='package-name',
            architecture='all'
        )
        step.output = StringIO()
        self.assertRaises(SystemExit, step.run)
        self.assertEqual(step.output.getvalue(), expected_output)

    @require_rpmlint
    def test_rpm(self):
        """
        rpmlint doesn't report filtered errors.
        """
        # The following warnings and errors are filtered.
        # - E: no-changelogname-tag
        # - W: no-documentation
        # - E: zero-length
        self.assert_lint(PackageTypes.RPM, b"""\
Package errors (package-name):
package-name.noarch: W: non-standard-group default
package-name.noarch: W: invalid-license Example
package-name.noarch: W: invalid-url URL: https://package.example/ \
<urlopen error [Errno -2] Name or service not known>
package-name.noarch: W: cross-directory-hard-link /foo/bar/Foo /opt/file
""")

    @require_lintian
    def test_deb(self):
        """
        lintian doesn't report filtered errors.
        """
        # The following warnings and errors are filtered.
        # - E: package-name: no-copyright-file
        # - E: package-name: dir-or-file-in-opt
        # - W: package-name: file-missing-in-md5sums .../changelog.Debian.gz
        self.assert_lint(PackageTypes.DEB, b"""\
Package errors (package-name):
W: package-name: unknown-section default
E: package-name: non-standard-toplevel-dir foo/
W: package-name: file-in-unusual-dir foo/bar/Bar
W: package-name: file-in-unusual-dir foo/bar/Foo
W: package-name: package-contains-hardlink foo/bar/Foo -> opt/file
""")


class OmnibusPackageBuilderTests(TestCase):
    """
    Tests for ``omnibus_package_builder``.
    """
    def test_centos_7(self):
        self.assert_omnibus_steps(
            distribution=Distribution(name='centos', version='7'),
            expected_category='Applications/System',
            expected_package_type=PackageTypes.RPM,
        )

    def test_ubuntu_14_04(self):
        self.assert_omnibus_steps(
            distribution=Distribution(name='ubuntu', version='14.04'),
            expected_category='admin',
            expected_package_type=PackageTypes.DEB,
        )

    def test_fedora_20(self):
        self.assert_omnibus_steps(
            distribution=Distribution(name='fedora', version='20'),
            expected_category='Applications/System',
            expected_package_type=PackageTypes.RPM,
        )

    def assert_omnibus_steps(
            self,
            distribution=Distribution(name='fedora', version='20'),
            expected_category='Applications/System',
            expected_package_type=PackageTypes.RPM,
            ):
        """
        A sequence of build steps is returned.
        """
        self.patch(packaging, 'CURRENT_DISTRIBUTION', distribution)

        fake_dependencies = {
            'python': [Dependency(package='python-dep')],
            'node': [Dependency(package='node-dep')],
            'cli': [Dependency(package='cli-dep')],
        }

        def fake_make_dependencies(
                package_name, package_version, distribution):
            return fake_dependencies[package_name]

        self.patch(packaging, 'make_dependencies', fake_make_dependencies)

        expected_destination_path = FilePath(self.mktemp())

        target_path = FilePath(self.mktemp())
        flocker_cli_path = target_path.child('flocker-cli')
        flocker_node_path = target_path.child('flocker-node')

        expected_virtualenv_path = FilePath('/opt/flocker')
        expected_prefix = FilePath('/')
        expected_epoch = PACKAGE.EPOCH.value
        expected_package_uri = b'https://www.example.com/foo/Bar-1.2.3.whl'
        expected_package_version_step = GetPackageVersion(
            virtualenv=VirtualEnv(root=expected_virtualenv_path),
            package_name='Flocker'
        )
        expected_version = DelayedRpmVersion(
            package_version_step=expected_package_version_step
        )
        expected_license = PACKAGE.LICENSE.value
        expected_url = PACKAGE.URL.value
        expected_vendor = PACKAGE.VENDOR.value
        expected_maintainer = PACKAGE.MAINTAINER.value

        expected = BuildSequence(
            steps=(
                # clusterhq-python-flocker steps
                InstallVirtualEnv(
                    virtualenv=VirtualEnv(root=expected_virtualenv_path)),
                InstallApplication(
                    virtualenv=VirtualEnv(root=expected_virtualenv_path),
                    package_uri=b'https://www.example.com/foo/Bar-1.2.3.whl',
                ),
                expected_package_version_step,
                BuildPackage(
                    package_type=expected_package_type,
                    destination_path=expected_destination_path,
                    source_paths={
                        expected_virtualenv_path: expected_virtualenv_path
                    },
                    name='clusterhq-python-flocker',
                    prefix=expected_prefix,
                    epoch=expected_epoch,
                    rpm_version=expected_version,
                    license=expected_license,
                    url=expected_url,
                    vendor=expected_vendor,
                    maintainer=expected_maintainer,
                    architecture='native',
                    description=PACKAGE_PYTHON.DESCRIPTION.value,
                    category=expected_category,
                    directories=[expected_virtualenv_path],
                    dependencies=[Dependency(package='python-dep')],
                ),
                LintPackage(
                    package_type=expected_package_type,
                    destination_path=expected_destination_path,
                    epoch=expected_epoch,
                    rpm_version=expected_version,
                    package='clusterhq-python-flocker',
                    architecture="native",
                ),

                # clusterhq-flocker-cli steps
                CreateLinks(
                    links=[
                        (FilePath('/opt/flocker/bin/flocker-deploy'),
                         flocker_cli_path),
                    ]
                ),
                BuildPackage(
                    package_type=expected_package_type,
                    destination_path=expected_destination_path,
                    source_paths={flocker_cli_path: FilePath("/usr/bin")},
                    name='clusterhq-flocker-cli',
                    prefix=expected_prefix,
                    epoch=expected_epoch,
                    rpm_version=expected_version,
                    license=expected_license,
                    url=expected_url,
                    vendor=expected_vendor,
                    maintainer=expected_maintainer,
                    architecture='all',
                    description=PACKAGE_CLI.DESCRIPTION.value,
                    category=expected_category,
                    dependencies=[Dependency(package='cli-dep')],
                ),
                LintPackage(
                    package_type=expected_package_type,
                    destination_path=expected_destination_path,
                    epoch=expected_epoch,
                    rpm_version=expected_version,
                    package='clusterhq-flocker-cli',
                    architecture="all",
                ),

                # clusterhq-flocker-node steps
                CreateLinks(
                    links=[
                        (FilePath('/opt/flocker/bin/flocker-reportstate'),
                         flocker_node_path),
                        (FilePath('/opt/flocker/bin/flocker-changestate'),
                         flocker_node_path),
                        (FilePath('/opt/flocker/bin/flocker-volume'),
                         flocker_node_path),
                    ]
                ),
                BuildPackage(
                    package_type=expected_package_type,
                    destination_path=expected_destination_path,
                    source_paths={flocker_node_path: FilePath("/usr/sbin")},
                    name='clusterhq-flocker-node',
                    prefix=expected_prefix,
                    epoch=expected_epoch,
                    rpm_version=expected_version,
                    license=expected_license,
                    url=expected_url,
                    vendor=expected_vendor,
                    maintainer=expected_maintainer,
                    architecture='all',
                    description=PACKAGE_NODE.DESCRIPTION.value,
                    category=expected_category,
                    dependencies=[Dependency(package='node-dep')],
                ),
                LintPackage(
                    package_type=expected_package_type,
                    destination_path=expected_destination_path,
                    epoch=expected_epoch,
                    rpm_version=expected_version,
                    package='clusterhq-flocker-node',
                    architecture="all",
                ),
            )
        )
        assert_equal_steps(
            self,
            expected,
            omnibus_package_builder(distribution=distribution,
                                    destination_path=expected_destination_path,
                                    package_uri=expected_package_uri,
                                    target_dir=target_path))


class DockerBuildOptionsTests(TestCase):
    """
    Tests for ``DockerBuildOptions``.
    """

    native_package_type = object()

    def setUp(self):
        """
        Patch ``admin.packaging._native_package_type`` to return a fixed value.
        """
        self.patch(
            packaging, '_native_package_type',
            lambda: self.native_package_type)

    def test_defaults(self):
        """
        ``DockerBuildOptions`` destination path defaults to the current working
        directory.
        """
        expected_defaults = {
            'destination-path': '.',
        }
        self.assertEqual(expected_defaults, DockerBuildOptions())

    def test_package_uri_missing(self):
        """
        ``DockerBuildOptions`` requires a single positional argument containing
        the URI of the Python package which is being packaged.
        """
        exception = self.assertRaises(
            UsageError, DockerBuildOptions().parseOptions, [])
        self.assertEqual('Wrong number of arguments.', str(exception))

    def test_package_uri_supplied(self):
        """
        ``DockerBuildOptions`` saves the supplied ``package-uri``.
        """
        expected_uri = 'http://www.example.com/foo-bar.whl'

        options = DockerBuildOptions()
        options.parseOptions([expected_uri])

        self.assertEqual(expected_uri, options['package-uri'])


class DockerBuildScriptTests(TestCase):
    """
    Tests for ``DockerBuildScript``.
    """
    def test_usage_error_status(self):
        """
        ``DockerBuildScript.main`` raises ``SystemExit`` if there are missing
        command line options.
        """
        fake_sys_module = FakeSysModule(argv=[])
        script = DockerBuildScript(sys_module=fake_sys_module)
        exception = self.assertRaises(SystemExit, script.main)
        self.assertEqual(1, exception.code)

    def test_usage_error_message(self):
        """
        ``DockerBuildScript.main`` prints a usage error to ``stderr`` if there
        are missing command line options.
        """
        fake_sys_module = FakeSysModule(argv=[])
        script = DockerBuildScript(sys_module=fake_sys_module)
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
        ``DockerBuildScript.build_command`` is ``omnibus_package_builder`` by
        default.
        """
        self.assertIs(omnibus_package_builder, DockerBuildScript.build_command)

    def test_run(self):
        """
        ``DockerBuildScript.main`` calls ``run`` on the instance returned by
        ``build_command``.
        """
        expected_destination_path = FilePath(self.mktemp())
        expected_package_uri = 'http://www.example.com/foo/bar.whl'
        fake_sys_module = FakeSysModule(
            argv=[
                'build-command-name',
                '--destination-path=%s' % (expected_destination_path.path,),
                expected_package_uri]
        )
        distribution = Distribution(name='test-distro', version='30')
        self.patch(packaging, 'CURRENT_DISTRIBUTION', distribution)
        script = DockerBuildScript(sys_module=fake_sys_module)
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
                 distribution=distribution)
        )]
        self.assertEqual(expected_build_arguments, arguments)
        self.assertTrue(build_step.ran)


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
            'distribution': None,
        }
        self.assertEqual(expected_defaults, BuildOptions())

    def test_distribution_missing(self):
        """
        ``BuildOptions.parseOptions`` raises ``UsageError`` if
        ``--distribution`` is not supplied.
        """
        options = BuildOptions()
        self.assertRaises(
            UsageError,
            options.parseOptions,
            ['http://example.com/fake/uri'])

    def test_package_uri_missing(self):
        """
        ``DockerBuildOptions`` requires a single positional argument containing
        the URI of the Python package which is being packaged.
        """
        exception = self.assertRaises(
            UsageError, BuildOptions().parseOptions, [])
        self.assertEqual('Wrong number of arguments.', str(exception))

    def test_package_options_supplied(self):
        """
        ``BuildOptions`` saves the supplied options.
        """
        expected_uri = 'http://www.example.com/foo-bar.whl'
        expected_distribution = 'ubuntu1404'
        options = BuildOptions()
        options.parseOptions(
            ['--distribution', expected_distribution, expected_uri])

        self.assertEqual(
            (expected_distribution, expected_uri),
            (options['distribution'], options['package-uri'])
        )


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
        ``BuildScript.build_command`` is ``build_in_docker`` by default.
        """
        self.assertIs(build_in_docker, BuildScript.build_command)

    def test_run(self):
        """
        ``BuildScript.main`` calls ``run`` on the instance returned by
        ``build_command``.
        """
        expected_destination_path = FilePath(self.mktemp())
        expected_distribution = 'centos7'
        expected_package_uri = 'http://www.example.com/foo/bar.whl'
        fake_sys_module = FakeSysModule(
            argv=[
                'build-command-name',
                '--destination-path', expected_destination_path.path,
                '--distribution=%s' % (expected_distribution,),
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
                 distribution=expected_distribution,
                 package_uri=expected_package_uri,
                 top_level=None)
        )]
        self.assertEqual(expected_build_arguments, arguments)
        self.assertTrue(build_step.ran)


class BuildInDockerFunctionTests(TestCase):
    """
    Tests for ``build_in_docker``.
    """
    def test_steps(self):
        """
        ``build_in_docker`` returns a ``BuildSequence`` comprising
        ``DockerBuild`` and ``DockerRun`` instances.
        """
        supplied_distribution = 'Foo'
        expected_tag = 'clusterhq/build-%s' % (supplied_distribution,)
        supplied_top_level = FilePath('/foo/bar')
        expected_build_directory = supplied_top_level.descendant(
            ['admin', 'build_targets', supplied_distribution])
        supplied_destination_path = FilePath('/baz/qux')
        expected_volumes = {
            FilePath('/output'): supplied_destination_path,
            FilePath('/flocker'): supplied_top_level,
        }
        expected_package_uri = 'http://www.example.com/foo/bar/whl'

        assert_equal_steps(
            test_case=self,
            expected=BuildSequence(
                steps=[
                    DockerBuild(
                        tag=expected_tag,
                        build_directory=expected_build_directory
                    ),
                    DockerRun(
                        tag=expected_tag,
                        volumes=expected_volumes,
                        command=[expected_package_uri]
                    ),
                ]
            ),
            actual=build_in_docker(
                destination_path=supplied_destination_path,
                distribution=supplied_distribution,
                top_level=supplied_top_level,
                package_uri=expected_package_uri
            )
        )


class MakeDependenciesTests(TestCase):
    """
    Tests for ``make_dependencies``.
    """
    def test_node(self):
        """
        ``make_dependencies`` includes the supplied ``version`` of
        ``clusterhq-python-flocker`` for ``clusterhq-flocker-node``.
        """
        expected_version = '1.2.3'
        self.assertIn(
            Dependency(
                package='clusterhq-python-flocker',
                compare='=',
                version=expected_version
            ),
            make_dependencies('node', expected_version,
                              Distribution(name='fedora', version='20'))
        )

    def test_cli(self):
        """
        ``make_dependencies`` includes the supplied ``version`` of
        ``clusterhq-python-flocker`` for ``clusterhq-flocker-cli``.
        """
        expected_version = '1.2.3'
        self.assertIn(
            Dependency(
                package='clusterhq-python-flocker',
                compare='=',
                version=expected_version
            ),
            make_dependencies('cli', expected_version,
                              Distribution(name='fedora', version='20'))
        )
