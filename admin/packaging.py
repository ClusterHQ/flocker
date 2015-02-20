# -*- test-case-name: admin.test.test_packaging -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Helper utilities for Flocker packaging.
"""

from functools import partial
import platform
import sys
import os
from subprocess import check_output, check_call, CalledProcessError, call
from tempfile import mkdtemp
from textwrap import dedent, fill

from twisted.python.constants import ValueConstant, Values
from twisted.python.filepath import FilePath
from twisted.python import usage, log

from characteristic import attributes, Attribute
import virtualenv

from .release import make_rpm_version


class PackageTypes(Values):
    """
    Constants representing supported target packaging formats.
    """
    RPM = ValueConstant('rpm')
    DEB = ValueConstant('deb')


# Associate package formats with platform operating systems.
PACKAGE_TYPE_MAP = {
    PackageTypes.RPM: ('fedora', 'centos'),
    PackageTypes.DEB: ('ubuntu',),
}

PACKAGE_NAME_FORMAT = {
    PackageTypes.RPM: '{}-{}-{}.{}.rpm',
    PackageTypes.DEB: '{}_{}-{}_{}.deb',
}

ARCH = {
    'all': {
        PackageTypes.RPM: 'noarch',
        PackageTypes.DEB: 'all',
    },
    'native': {  # HACK
        PackageTypes.RPM: 'x86_64',
        PackageTypes.DEB: 'amd64',
    },
}


def package_filename(package_type, package, architecture, rpm_version):
    package_name_format = PACKAGE_NAME_FORMAT[package_type]
    return package_name_format.format(
        package, rpm_version.version,
        rpm_version.release, ARCH[architecture][package_type])


@attributes(['name', 'version'])
class Distribution(object):
    """
    A linux distribution.

    :ivar bytes name: The name of the distribution.
    :ivar bytes version: The version of the distribution.
    """

    @classmethod
    def _get_current_distribution(klass):
        """
        :return: A ``Distribution`` representing the current platform.
        """
        name, version, id = (
            platform.linux_distribution(full_distribution_name=False))
        return klass(name=name.lower(), version=version)

    def package_type(self):
        distribution_name = self.name.lower()

        for package_type, distribution_names in PACKAGE_TYPE_MAP.items():
            if distribution_name.lower() in distribution_names:
                return package_type
        else:
            raise ValueError("Unknown distribution.", distribution_name)


CURRENT_DISTRIBUTION = Distribution._get_current_distribution()


def _native_package_type():
    """
    :return: The ``bytes`` name of the native package format for this platform.
    """
    distribution_name = CURRENT_DISTRIBUTION.name.lower()

    for package_type, distribution_names in PACKAGE_TYPE_MAP.items():
        if distribution_name.lower() in distribution_names:
            return package_type
    else:
        raise ValueError("Unknown distribution.", distribution_name)


@attributes(['steps'])
class BuildSequence(object):
    """
    Run the supplied ``steps`` consecutively.

    :ivar tuple steps: A sequence of steps.
    """
    def run(self):
        for step in self.steps:
            step.run()


def run_command(args, added_env=None, cwd=None):
    """
    Run a subprocess and return its output. The command line and its
    environment are logged for debugging purposes.

    :param dict env: Addtional environment variables to pass.

    :return: The output of the command.
    """
    log.msg(
        format="Running %(args)r with environment %(env)r "
               "and working directory %(cwd)s",
        args=args, env=added_env, cwd=cwd)
    if added_env:
        env = os.environ.copy()
        env.update(env)
    else:
        env = None
    try:
        return check_output(args=args, env=env, cwd=cwd,)
    except CalledProcessError as e:
        print e.output


@attributes([
    Attribute('package'),
    Attribute('compare', default_value=None),
    Attribute('version', default_value=None)])
class Dependency(object):
    """
    A package dependency.

    :ivar bytes package: The name of the dependency package.
    :ivar bytes compare: The operator to use when comparing required and
        available versions of the dependency package.
    :ivar bytes version: The version of the dependency package.
    """
    def __init__(self):
        """
        :raises ValueError: If ``compare`` and ``version`` values are not
            compatible.
        """
        if (self.compare is None) != (self.version is None):
            raise ValueError(
                "Must specify both or neither compare and version.")

    def format(self, package_type):
        """
        :return: A ``bytes`` representation of the desired version comparison
            which can be parsed by the package management tools associated with
            ``package_type``.

        :raises: ``ValueError`` if supplied with an unrecognised
            ``package_type``.
        """
        if package_type == PackageTypes.DEB:
            if self.version:
                return "%s (%s %s)" % (
                    self.package, self.compare, self.version)
            else:
                return self.package
        elif package_type == PackageTypes.RPM:
            if self.version:
                return "%s %s %s" % (self.package, self.compare, self.version)
            else:
                return self.package
        else:
            raise ValueError("Unknown package type.")


# The minimum required versions of Docker and ZFS. The package names vary
# between operating systems and are supplied later.
DockerDependency = partial(Dependency, compare='>=', version='1.3.0')
# This ensures that servers with the broken docker-io-1.4.1 package get
# upgraded when Flocker is installed.
# See https://bugzilla.redhat.com/show_bug.cgi?id=1185423
# The working 1.4.1-8 package is temporarily being hosted in the ClusterHQ
# repo, but will soon be backported to Fedora20.
# See https://admin.fedoraproject.org/updates/docker-io-1.4.1-8.fc20
# In future this specific minimum version dependency can be removed.
# See https://clusterhq.atlassian.net/browse/FLOC-1293
FedoraDockerDependency = partial(
    Dependency, package='docker-io', compare='>=', version='1.4.1-8.fc20')

ZFSDependency = partial(Dependency, compare='>=', version='0.6.3')

# We generate three packages.  ``clusterhq-python-flocker`` contains the entire
# code base.  ``clusterhq-flocker-cli`` and ``clusterhq-flocker-node`` are meta
# packages which symlink only the cli or node specific scripts and load only
# the dependencies required to satisfy those scripts.  This map represents the
# dependencies for each of those three packages and accounts for differing
# dependency package names and versions on various platforms.
DEPENDENCIES = {
    'python': {
        'fedora': (
            Dependency(package='python'),
        ),
        'centos': (
            Dependency(package='python'),
        ),
        'ubuntu': (
            Dependency(package='python2.7'),
        ),
    },
    'node': {
        'fedora': (
            FedoraDockerDependency(),
            Dependency(package='/usr/sbin/iptables'),
            ZFSDependency(package='zfs'),
            Dependency(package='openssh-clients'),
        ),
        'centos': (
            DockerDependency(package='docker'),
            Dependency(package='/usr/sbin/iptables'),
            ZFSDependency(package='zfs'),
            Dependency(package='openssh-clients'),
        ),
        'ubuntu': (
            # trust-updates version
            DockerDependency(package='docker.io'),
            Dependency(package='iptables'),
            ZFSDependency(package='zfsutils'),
            Dependency(package='openssh-client'),
        ),
    },
    'cli': {
        'fedora': (
            Dependency(package='openssh-clients'),
        ),
        'centos': (
            Dependency(package='openssh-clients'),
        ),
        'ubuntu': (
            Dependency(package='openssh-client'),
        ),
    },
}


def make_dependencies(package_name, package_version, distribution):
    """
    Add the supplied version of ``python-flocker`` to the base dependency lists
    defined in ``DEPENDENCIES``.

    :param bytes package_name: The name of the flocker package to generate
        dependencies for.
    :param bytes package_version: The flocker version.
    :param Distribution distribution: The distribution for which to
        generate dependencies.

    :return: A list of ``Dependency`` instances.
    """
    dependencies = DEPENDENCIES[package_name][distribution.name]
    if package_name in ('node', 'cli'):
        dependencies += (
            Dependency(
                package='clusterhq-python-flocker',
                compare='=',
                version=package_version),)
    return dependencies


def create_virtualenv(root):
    """
    Create a virtualenv in ``root``.

    :param FilePath root: The directory in which to install a virtualenv.
    :returns: A ``VirtualEnv`` instance.
    """
    # We call ``virtualenv`` as a subprocess rather than as a library, so that
    # we can turn off Python byte code compilation.
    run_command(
        ['virtualenv', '--python=/usr/bin/python2.7', '--quiet', root.path],
        added_env=dict(PYTHONDONTWRITEBYTECODE='1')
    )
    # XXX: Virtualenv doesn't link to pyc files when copying its bootstrap
    # modules. See https://github.com/pypa/virtualenv/issues/659
    for module_name in virtualenv.REQUIRED_MODULES:
        py_base = root.descendant(
            ['lib', 'python2.7', module_name])
        py = py_base.siblingExtension('.py')
        if py.exists() and py.islink():
            pyc = py_base.siblingExtension('.pyc')
            py_target = py.realpath()
            pyc_target = FilePath(
                py_target.splitext()[0]).siblingExtension('.pyc')

            if pyc.exists():
                pyc.remove()

            if pyc_target.exists():
                pyc_target.linkTo(pyc)

    return VirtualEnv(root=root)


@attributes(['virtualenv'])
class InstallVirtualEnv(object):
    """
    Install a virtualenv in the supplied ``target_path``.

    :ivar FilePath target_path: The path to a directory in which to create the
        virtualenv.
    """
    _create_virtualenv = staticmethod(create_virtualenv)

    def run(self):
        self._create_virtualenv(root=self.virtualenv.root)


@attributes(['name', 'version'])
class PythonPackage(object):
    """
    A model representing a single pip installable Python package.

    :ivar bytes name: The name of the package.
    :ivar bytes version: The version of the package.
    """


@attributes(['root'])
class VirtualEnv(object):
    """
    A model representing a virtualenv directory.
    """
    def install(self, package_uri):
        """
        Install package and its dependencies into this virtualenv.
        """
        # We can't just call pip directly, because in the virtualenvs created
        # in tests, the shebang line becomes too long and triggers an
        # error. See http://www.in-ulm.de/~mascheck/various/shebang/#errors
        python_path = self.root.child('bin').child('python').path

        run_command(
            [python_path, '-m', 'pip', '--quiet', 'install', package_uri],
        )


@attributes(['virtualenv', 'package_uri'])
class InstallApplication(object):
    """
    Install the supplied ``package_uri`` using the supplied ``virtualenv``.

    :ivar VirtualEnv virtualenv: The virtual environment in which to install
       ``package``.
    :ivar bytes package_uri: A pip compatible URI.
    """
    def run(self):
        self.virtualenv.install(self.package_uri)


@attributes(['links'])
class CreateLinks(object):
    """
    Create symlinks to the files in ``links``.
    """
    def run(self):
        """
        If link is a directory, the target filename will be used as the link
        name within that directory.
        """
        for target, link in self.links:
            if link.isdir():
                name = link.child(target.basename())
            else:
                name = link
            target.linkTo(name)


@attributes(['virtualenv', 'package_name'])
class GetPackageVersion(object):
    """
    Record the version of ``package_name`` installed in ``virtualenv_path`` by
    examining ``<package_name>.__version__``.

    :ivar VirtualEnv virtualenv: The ``virtualenv`` containing the package.
    :ivar bytes package_name: The name of the package whose version will be
        recorded.
    :ivar version: The version string of the supplied package. Default is
        ``None`` until the step has been run. or if the supplied

    :raises: If ``package_name`` is not found.
    """
    version = None

    def run(self):
        python_path = self.virtualenv.root.child('bin').child('python').path
        output = check_output(
            [python_path,
             '-c', '; '.join([
                 'from sys import stdout',
                 'stdout.write(__import__(%r).__version__)' % self.package_name
             ])])

        self.version = output


@attributes([
    'package_type', 'destination_path', 'source_paths', 'name', 'prefix',
    'epoch', 'rpm_version', 'license', 'url', 'vendor', 'maintainer',
    'architecture', 'description', 'dependencies', 'category',
    Attribute('directories', default_factory=list),
    'post_install',
])
class BuildPackage(object):
    """
    Use ``fpm`` to build an RPM file from the supplied ``source_path``.

    :ivar package_type: A package type constant from ``PackageTypes``.
    :ivar FilePath destination_path: The path in which to save the resulting
        RPM package file.
    :ivar dict source_paths: A dictionary mapping paths in the filesystem to
        the path in the package.
    :ivar bytes name: The name of the package.
    :ivar FilePath prefix: The path beneath which the packaged files will be
         installed.
    :ivar bytes epoch: An integer string tag used to help RPM determine version
        number ordering.
    :ivar rpm_version rpm_version: An object representing an RPM style version
        containing a release and a version attribute.
    :ivar bytes license: The name of the license under which this package is
        released.
    :ivar bytes url: The URL of the source of this package.
    :ivar unicode vendor: The name of the package vendor.
    :ivar bytes maintainer: The email address of the package maintainer.
    :ivar bytes architecture: The OS architecture for which this package is
        targeted. Default ``None`` means architecture independent.
    :ivar unicode description: A description of the package.
    :ivar unicode category: The category of the package.
    :ivar list dependencies: The list of dependencies of the package.
    :ivar list directories: List of directories the package should own.
    """
    def run(self):
        architecture = self.architecture

        command = [
            'fpm',
            '--force',
            '-s', 'dir',
            '-t', self.package_type.value,
            '--package', self.destination_path.path,
            '--name', self.name,
            '--prefix', self.prefix.path,
            '--version', self.rpm_version.version,
            '--epoch', self.epoch,
            '--iteration', self.rpm_version.release,
            '--license', self.license,
            '--url', self.url,
            '--vendor', self.vendor,
            '--maintainer', self.maintainer,
            '--architecture', architecture,
            '--description', self.description,
            # From `%firewalld_reload`
            '--after-install', self.post_install.path,
            '--category', self.category,
        ]

        command = []
        for requirement in self.dependencies:
            command.extend(
                ['--depends', requirement.format(self.package_type)])

        for directory in self.directories:
            command.extend(
                ['--directories', directory.path])

        if self.post_install:
            command.extend(
                ['--post-install', self.post_install.path])

        for source_path, package_path in self.source_paths.items():
            # Think of /= as a separate operator. It causes fpm to copy the
            # content of the directory rather than the directory its self.
            command.append(
                "%s/=%s" % (source_path.path, package_path.path))

        run_command(command)


@attributes(['package_version_step'])
class DelayedRpmVersion(object):
    """
    Pretend to be an ``rpm_version`` instance providing a ``version`` and
    ``release`` attribute.

    The values of these attributes will be calculated from the Python version
    string read from a previous ``GetPackageVersion`` build step.

    :ivar GetPackageVersion package_version_step: An instance of
        ``GetPackageVersion`` whose ``run`` method will have been called and
        from which the version string will be read.
    """
    _rpm_version = None

    @property
    def rpm_version(self):
        """
        :return: An ``rpm_version`` and cache it.
        """
        if self._rpm_version is None:
            self._rpm_version = make_rpm_version(
                self.package_version_step.version
            )
        return self._rpm_version

    @property
    def version(self):
        """
        :return: The ``version`` string.
        """
        return self.rpm_version.version

    @property
    def release(self):
        """
        :return: The ``release`` string.
        """
        return self.rpm_version.release

    def __str__(self):
        return self.rpm_version.version + '-' + self.rpm_version.release

IGNORED_WARNINGS = {
    PackageTypes.RPM: (
        # Ignore the summary line rpmlint prints.
        # We always check a single package, so we can hardcode the numbers.
        '1 packages and 0 specfiles checked;',

        # This isn't an distribution package so we deliberately install in /opt
        'dir-or-file-in-opt',
        # We don't care enough to fix this
        'python-bytecode-inconsistent-mtime',
        # /opt/flocker/lib/python2.7/no-global-site-packages.txt will be empty.
        'zero-length',

        # cli/node packages have symlink to base package
        'dangling-symlink',

        # Should be fixed
        'no-documentation',
        'no-manual-page-for-binary',
        # changelogs are elsewhere
        'no-changelogname-tag',

        # virtualenv's interpreter is correct.
        'wrong-script-interpreter',

        # rpmlint on CentOS 7 doesn't see python in the virtualenv.
        'no-binary',

        # These are in our dependencies.
        'incorrect-fsf-address',
        'pem-certificate',
        'non-executable-script',
        'devel-file-in-non-devel-package',
        'unstripped-binary-or-object',

        # FIXME
        'only-non-binary-in-usr-lib',
        'non-conffile-in-etc /etc/ufw/applications.d/flocker-control',
    ),
# See https://www.debian.org/doc/manuals/developers-reference/tools.html#lintian  # noqa
    PackageTypes.DEB: (
        # This isn't an distribution package so we deliberately install in /opt
        'dir-or-file-in-opt',

        # virtualenv's interpreter is correct.
        'wrong-path-for-interpreter',
        # Virtualenv creates symlinks for local/{bin,include,lib}. Ignore them.
        'symlink-should-be-relative',

        # We depend on python2.7 which depends on libc
        'missing-dependency-on-libc',

        # We are installing in a virtualenv, so we can't easily use debian's
        # bytecompiling infrastructure. It doesn't provide any benefit, either.
        'package-installs-python-bytecode',

        # https://github.com/jordansissel/fpm/issues/833
        ('file-missing-in-md5sums '
         'usr/share/doc/'),

        # lintian expects python dep for .../python shebang lines.
        # We are in a virtualenv that points at python2.7 explictly and has
        # that dependency.
        'python-script-but-no-python-dep',

        # Should be fixed
        'binary-without-manpage',
        'no-copyright-file',

        # These are in our dependencies.
        'script-not-executable',
        'embedded-javascript-library',
        'extra-license-file',
        'unstripped-binary-or-object',

        # Werkzeug installs various images with executable permissions.
        # https://github.com/mitsuhiko/werkzeug/issues/629
        # Fixed upstream, but not released.
        'executable-not-elf-or-script',

        # Our omnibus packages are never going to be used by upstream so
        # there's no bug to close.
        # https://lintian.debian.org/tags/new-package-should-close-itp-bug.html
        'new-package-should-close-itp-bug'
    ),
}


@attributes([
    'package_type',
    'destination_path',
    'epoch',
    'rpm_version',
    'package',
    'architecture',
])
class LintPackage(object):
    """
    Run package linting tool against a package and fail if there are any errors
    or warnings that aren't whitelisted.
    """
    output = sys.stdout

    @staticmethod
    def check_lint_output(warnings, ignored_warnings):
        """
        Filter the output of a linting tool against a list of ignored
        warnings.

        :param list warnings: List of warnings produced.
        :param list ignored_warnings: List of warnings to ignore. A warning is
            ignored it it has a substring matching something in this list.
        """
        unacceptable = []
        for warning in warnings:
            # Ignore certain warning lines
            for ignored in ignored_warnings:
                if ignored in warning:
                    break
            else:
                unacceptable.append(warning)
        return unacceptable

    def run(self):
        filename = package_filename(
            package_type=self.package_type,
            package=self.package, rpm_version=self.rpm_version,
            architecture=self.architecture)

        output_file = self.destination_path.child(filename)

        try:
            check_output([
                {
                    PackageTypes.RPM: 'rpmlint',
                    PackageTypes.DEB: 'lintian',
                }[self.package_type],
                output_file.path,
            ])
        except CalledProcessError as e:
            results = self.check_lint_output(
                warnings=e.output.splitlines(),
                ignored_warnings=IGNORED_WARNINGS[self.package_type],
            )

            if results:
                self.output.write("Package errors (%s):\n" % (self.package))
                self.output.write('\n'.join(results) + "\n")
                raise SystemExit(1)


class PACKAGE(Values):
    """
    Constants for ClusterHQ specific metadata that we add to all three
    packages.
    """
    EPOCH = ValueConstant(b'0')
    LICENSE = ValueConstant(b'ASL 2.0')
    URL = ValueConstant(b'https://clusterhq.com')
    VENDOR = ValueConstant(b'ClusterHQ')
    MAINTAINER = ValueConstant(b'ClusterHQ <contact@clusterhq.com>')


class PACKAGE_PYTHON(PACKAGE):
    DESCRIPTION = ValueConstant(
        'Docker orchestration and volume management tool\n'
        + fill('This is the base package of scripts and libraries.', 79)
    )


class PACKAGE_CLI(PACKAGE):
    DESCRIPTION = ValueConstant(
        'Docker orchestration and volume management tool\n'
        + fill('This meta-package contains links to the Flocker client '
               'utilities, and has only the dependencies required to run '
               'those tools', 79)
    )


class PACKAGE_NODE(PACKAGE):
    DESCRIPTION = ValueConstant(
        'Docker orchestration and volume management tool\n'
        + fill('This meta-package contains links to the Flocker node '
               'utilities, and has only the dependencies required to run '
               'those tools', 79)
    )


def omnibus_package_builder(
        distribution, destination_path, package_uri, base_path, target_dir=None):
    """
    Build a sequence of build steps which when run will generate a package in
    ``destination_path``, containing the package installed from ``package_uri``
    and all its dependencies.

    The steps are:

    * Create a virtualenv with ``--system-site-packages`` which allows certain
      python libraries to be supplied by the operating system.

    * Install Flocker and all its dependencies in the virtualenv.

    * Find the version of the installed Flocker package, as reported by
      ``pip``.

    * Build an RPM from the virtualenv directory using ``fpm``.

    :param package_type: A package type constant from ``PackageTypes``.
    :param FilePath destination_path: The path to a directory in which to save
        the resulting RPM file.
    :param Package package: A ``Package`` instance with a ``pip install``
        compatible package URI.
    :param FilePath target_dir: An optional path in which to create the
        virtualenv from which the package will be generated. Default is a
        temporary directory created using ``mkdtemp``.
    :return: A ``BuildSequence`` instance containing all the required build
        steps.
    """
    if target_dir is None:
        target_dir = FilePath(mkdtemp())

    flocker_cli_path = target_dir.child('flocker-cli')
    flocker_cli_path.makedirs()
    flocker_node_path = target_dir.child('flocker-node')
    flocker_node_path.makedirs()
    # Flocker is installed in /opt.
    # See http://fedoraproject.org/wiki/Packaging:Guidelines#Limited_usage_of_.2Fopt.2C_.2Fetc.2Fopt.2C_and_.2Fvar.2Fopt  # noqa
    virtualenv_dir = FilePath('/opt/flocker')

    virtualenv = VirtualEnv(root=virtualenv_dir)

    get_package_version_step = GetPackageVersion(
        virtualenv=virtualenv, package_name='flocker')
    rpm_version = DelayedRpmVersion(
        package_version_step=get_package_version_step)

    category = {
        PackageTypes.RPM: 'Applications/System',
        PackageTypes.DEB: 'admin',
    }[distribution.package_type()]

    return BuildSequence(
        steps=(
            InstallVirtualEnv(virtualenv=virtualenv),
            InstallApplication(virtualenv=virtualenv,
                               package_uri=package_uri),
            # get_package_version_step must be run before steps that reference
            # rpm_version
            get_package_version_step,
            BuildPackage(
                package_type=distribution.package_type(),
                destination_path=destination_path,
                source_paths={virtualenv_dir: virtualenv_dir},
                name='clusterhq-python-flocker',
                prefix=FilePath('/'),
                epoch=PACKAGE.EPOCH.value,
                rpm_version=rpm_version,
                license=PACKAGE.LICENSE.value,
                url=PACKAGE.URL.value,
                vendor=PACKAGE.VENDOR.value,
                maintainer=PACKAGE.MAINTAINER.value,
                architecture='native',
                description=PACKAGE_PYTHON.DESCRIPTION.value,
                category=category,
                dependencies=make_dependencies(
                    'python', rpm_version, distribution),
                directories=[virtualenv_dir],
            ),
            LintPackage(
                package_type=distribution.package_type(),
                destination_path=destination_path,
                epoch=PACKAGE.EPOCH.value,
                rpm_version=rpm_version,
                package='clusterhq-python-flocker',
                architecture='native',
            ),

            # flocker-cli steps

            # First, link command-line tools that should be available.  If you
            # change this you may also want to change entry_points in setup.py.
            CreateLinks(
                links=[
                    (FilePath('/opt/flocker/bin/flocker-deploy'),
                     flocker_cli_path),
                ]
            ),
            BuildPackage(
                package_type=distribution.package_type(),
                destination_path=destination_path,
                source_paths={flocker_cli_path: FilePath("/usr/bin")},
                name='clusterhq-flocker-cli',
                prefix=FilePath('/'),
                epoch=PACKAGE.EPOCH.value,
                rpm_version=rpm_version,
                license=PACKAGE.LICENSE.value,
                url=PACKAGE.URL.value,
                vendor=PACKAGE.VENDOR.value,
                maintainer=PACKAGE.MAINTAINER.value,
                architecture='all',
                description=PACKAGE_CLI.DESCRIPTION.value,
                category=category,
                dependencies=make_dependencies(
                    'cli', rpm_version, distribution),
            ),
            LintPackage(
                package_type=distribution.package_type(),
                destination_path=destination_path,
                epoch=PACKAGE.EPOCH.value,
                rpm_version=rpm_version,
                package='clusterhq-flocker-cli',
                architecture='all',
            ),

            # flocker-node steps

            # First, link command-line tools that should be available.  If you
            # change this you may also want to change entry_points in setup.py.
            CreateLinks(
                links=[
                    (FilePath('/opt/flocker/bin/flocker-reportstate'),
                     flocker_node_path),
                    (FilePath('/opt/flocker/bin/flocker-changestate'),
                     flocker_node_path),
                    (FilePath('/opt/flocker/bin/flocker-volume'),
                     flocker_node_path),
                    (FilePath('/opt/flocker/bin/flocker-control'),
                     flocker_node_path),
                    (FilePath('/opt/flocker/bin/flocker-zfs-agent'),
                     flocker_node_path),
                ]
            ),
            BuildPackage(
                package_type=distribution.package_type(),
                destination_path=destination_path,
                source_paths={
                    flocker_node_path: FilePath("/usr/sbin"),
                    # Fedora/CentOS firewall configuration
                    base_path.sibling('package-files').child('flocker-control.firewalld.xml'):
                        FilePath("/usr/lib/firewalld/services/flocker-control.xml"),
                    # Ubuntu firewall configuration
                    base_path.sibling('package-files').child('flocker-control.ufw'):
                        FilePath("/etc/ufw/applications.d/flocker-control"),
                },
                name='clusterhq-flocker-node',
                prefix=FilePath('/'),
                epoch=PACKAGE.EPOCH.value,
                rpm_version=rpm_version,
                license=PACKAGE.LICENSE.value,
                url=PACKAGE.URL.value,
                vendor=PACKAGE.VENDOR.value,
                maintainer=PACKAGE.MAINTAINER.value,
                architecture='all',
                description=PACKAGE_NODE.DESCRIPTION.value,
                category=category,
                dependencies=make_dependencies(
                    'node', rpm_version, distribution),
            ),
            LintPackage(
                package_type=distribution.package_type(),
                destination_path=destination_path,
                epoch=PACKAGE.EPOCH.value,
                rpm_version=rpm_version,
                package='clusterhq-flocker-node',
                architecture='all',
            ),
        )
    )


@attributes(['tag', 'build_directory'])
class DockerBuild(object):
    """
    Build a docker image and tag it.

    :ivar bytes tag: The tag name which will be assigned to the generated
        docker image.
    :ivar FilePath build_directory: The directory containing the ``Dockerfile``
        to build.
    """
    def run(self):
        check_call(
            ['docker', 'build', '--tag', self.tag, self.build_directory.path])


@attributes(['tag', 'volumes', 'command'])
class DockerRun(object):
    """
    Run a docker image with the supplied volumes and command line arguments.

    :ivar bytes tag: The tag name of the image to run.
    :ivar dict volumes: A dict mapping ``FilePath`` container path to
        ``FilePath`` host path for each docker volume.
    :ivar list command: The command line arguments which will be supplied to
        the docker image entry point.
    """
    def run(self):
        volume_options = []
        for container, host in self.volumes.iteritems():
            volume_options.extend(
                ['--volume', '%s:%s' % (host.path, container.path)])

        result = call(
            ['docker', 'run', '--rm']
            + volume_options + [self.tag] + self.command)
        if result:
            raise SystemExit(result)


def build_in_docker(destination_path, distribution, top_level, package_uri):
    """
    Build a flocker package for a given ``distribution`` inside a clean docker
    container of that ``distribution``.

    :param FilePath destination_path: The directory to which the generated
         packages will be copied.
    :param bytes distribution: The distribution name for which to build a
        package.
    :param FilePath top_level: The Flocker source code directory.
    :param bytes package_uri: The ``pip`` style python package URI to install.
    """
    if destination_path.exists() and not destination_path.isdir():
        raise ValueError("go away")

    volumes = {
        FilePath('/output'): destination_path,
        FilePath('/flocker'): top_level,
    }

    # Special case to allow building the currently checked out Flocker code.
    if package_uri == top_level.path:
        package_uri = '/flocker'

    tag = "clusterhq/build-%s" % (distribution,)
    build_directory = top_level.descendant(
        ['admin', 'build_targets', distribution])

    return BuildSequence(
        steps=[
            DockerBuild(
                tag=tag,
                build_directory=build_directory
            ),
            DockerRun(
                tag=tag,
                volumes=volumes,
                command=[package_uri]
            ),
        ])


class DockerBuildOptions(usage.Options):
    """
    Command line options for the ``build-package-entrypoint`` tool.
    """
    synopsis = 'build-package-entrypoint [options] <package-uri>'

    optParameters = [
        ['destination-path', 'd', '.',
         'The path to a directory in which to create package files and '
         'artifacts.'],
    ]

    longdesc = dedent("""\
    Arguments:

    <package-uri>: The Python package url or path to install using ``pip``.
    """)

    def parseArgs(self, package_uri):
        """
        The Python package to install.
        """
        self['package-uri'] = package_uri

    def postOptions(self):
        """
        Coerce paths to ``FilePath``.
        """
        self['destination-path'] = FilePath(self['destination-path'])


class DockerBuildScript(object):
    """
    Check supplied command line arguments, print command line argument errors
    to ``stderr`` otherwise build the RPM package.

    :ivar build_command: The function responsible for building the
        package. Allows the command to be overridden in tests.
    """
    build_command = staticmethod(omnibus_package_builder)

    def __init__(self, sys_module=None):
        """
        :param sys_module: A ``sys`` like object whose ``argv``, ``stdout`` and
            ``stderr`` will be used in the script. Can be overridden in tests
            to make assertions about the script argument parsing and output
            printing. Default is ``sys``.
        """
        if sys_module is None:
            sys_module = sys
        self.sys_module = sys_module

    def main(self, top_level=None, base_path=None):
        """
        Check command line arguments and run the build steps.

        :param top_level: ignored.
        :param base_path: ignored.
        """
        options = DockerBuildOptions()

        try:
            options.parseOptions(self.sys_module.argv[1:])
        except usage.UsageError as e:
            self.sys_module.stderr.write("%s\n" % (options,))
            self.sys_module.stderr.write("%s\n" % (e,))
            raise SystemExit(1)

        self.build_command(
            distribution=CURRENT_DISTRIBUTION,
            destination_path=options['destination-path'],
            package_uri=options['package-uri'],
            base_path=base_path,
        ).run()

docker_main = DockerBuildScript().main


class BuildOptions(usage.Options):
    """
    Command line options for the ``build-package`` tool.
    """
    synopsis = 'build-package [options] <package-uri>'

    optParameters = [
        ['destination-path', 'd', '.',
         'The path to a directory in which to create package files and '
         'artifacts.'],
        ['distribution', None, None,
         'The target distribution. '
         'One of fedora-20, centos-7, or ubuntu-14.04.'],
    ]

    longdesc = dedent("""\
    Arguments:

    <package-uri>: The Python package url or path to install using ``pip``.
    """)

    def parseArgs(self, package_uri):
        """
        The Python package to install.
        """
        self['package-uri'] = package_uri

    def postOptions(self):
        """
        Coerce paths to ``FilePath`` and select a suitable ``native``
        ``package-type``.
        """
        self['destination-path'] = FilePath(self['destination-path'])
        if self['distribution'] is None:
            raise usage.UsageError('Must specify --distribution.')


class BuildScript(object):
    """
    Check supplied command line arguments, print command line argument errors
    to ``stderr`` otherwise build the RPM package.

    :ivar build_command: The function responsible for building the
        package. Allows the command to be overridden in tests.
    """
    build_command = staticmethod(build_in_docker)

    def __init__(self, sys_module=None):
        """
        :param sys_module: A ``sys`` like object whose ``argv``, ``stdout`` and
            ``stderr`` will be used in the script. Can be overridden in tests
            to make assertions about the script argument parsing and output
            printing. Default is ``sys``.
        """
        if sys_module is None:
            sys_module = sys
        self.sys_module = sys_module

    def main(self, top_level=None, base_path=None):
        """
        Check command line arguments and run the build steps.

        :param top_level: The path to the root of the checked out flocker
            directory.
        :param base_path: ignored.
        """
        options = BuildOptions()

        try:
            options.parseOptions(self.sys_module.argv[1:])
        except usage.UsageError as e:
            self.sys_module.stderr.write("%s\n" % (options,))
            self.sys_module.stderr.write("%s\n" % (e,))
            raise SystemExit(1)

        self.build_command(
            destination_path=options['destination-path'],
            package_uri=options['package-uri'],
            top_level=top_level,
            distribution=options['distribution'],
        ).run()

main = BuildScript().main
