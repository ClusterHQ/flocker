# -*- test-case-name: admin.test.test_packaging -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Helper utilities for Flocker packaging.

Notes:

    Motivation:
    * We depend on libraries which are not packaged for the target OS.
    * We depend on newer versions of libraries which have not yet been included
      in the target OS.

    Disadvantages:
    * We won't be able to take advantage of library security updates shipped by
      the target OS.
      * But by shipping our own separate dependency packages we will need to be
        responsible for shipping security patches in those packages.
      * And rather than being responsible only for the security of Flocker, we
        become responsible for the security of all other packages that depend
        on that package.
    * Packages will be larger.

    Followup Issues:
    * Update all pinned dependencies to instead be minimum dependencies.
      * This means that as and when sufficiently new versions of our
        dependencies are introduced upstream, we can remove them from our sumo
        build.
      * We'll need to keep track of which of our dependencies are provided on
        each platform and somehow omit those from the build for that
        platform.
      * Those dependencies which are either too old or which are not packaged
        will be imported from the sumo virtualenv in preference.
      * Eventually we hope that all our dependencies will filter upstream and
        we will no longer have to bundle them; at which point the `flocker`
        package itself may be ready to be packaged by upstream distributions.

    Ticket refs:
         * https://github.com/ClusterHQ/flocker/issues/88

    Issue: CI integration (??):
    Update buildbot to build RPMs using new build scripts
    * Issue: create deb, mac, gentoo build slave
    * Issue: install from resulting package from repo and run test suite

    Issue: Client package build (??):
    Sumo packaging of flocker-deploy
    * For deb, RPM, and mac (via homebrew or ...)
    * Proper mac packages. See
      http://stackoverflow.com/questions/11487596/making-os-x-installer-packages-like-a-pro-xcode4-developer-id-mountain-lion-re

    Client package CI integration

    Misc:
    * separate stable and testing repos for deb and rpm
    * update python-flocker.spec.in requirements (remove most of them)
    * maybe even remove the spec file template and generate_spec function
      entirely (do we need it?)
    * do we still need to build an SRPM?
    * automatically build a wheel
    * automatically build an sdist

    Similar / Related Systems:
    * http://dh-virtualenv.readthedocs.org/en/latest/info.html
    * https://github.com/mozilla/socorro/blob/master/scripts/install.sh and
      https://github.com/mozilla/socorro/blob/master/scripts/package.sh and
      http://socorro.readthedocs.org/en/latest/installation/install-src-prod.html
    *
"""
import platform
import sys
from subprocess import check_call, check_output
from tempfile import mkdtemp
from textwrap import dedent

from twisted.python.filepath import FilePath
from twisted.python import usage

from characteristic import attributes

from .release import make_rpm_version


# RPM style 'Requires' values which will be added to the Flocker RPM headers.
FLOCKER_RPM_DEPENDENCIES = (
    'docker-io',
    '/usr/sbin/iptables',
    'zfs',
)

# Associate package formats with platform operating systems.
PACKAGE_TYPE_MAP = dict(
    rpm=('fedora',),
    deb=('ubuntu',),
)

def _native_package_type():
    """
    :return: The ``bytes`` name of the native package format for this platform.
    """
    (distribution_name,
     distribution_version,
     distribution_id) = platform.linux_distribution()

    for package_type, distribution_names in PACKAGE_TYPE_MAP.items():
        if distribution_name.lower() in distribution_names:
            return package_type


@attributes(['steps'])
class BuildSequence(object):
    """
    Run the supplied ``steps`` consecutively.

    :ivar tuple steps: A sequence of steps.
    """
    def run(self):
        for step in self.steps:
            step.run()


@attributes(['target_path'])
class InstallVirtualEnv(object):
    """
    Install a virtualenv in the supplied ``target_path``.

    We call ``virtualenv`` as a subprocess rather than as a library, so that we
    can turn off Python byte code compilation.

    :ivar FilePath target_path: The path to a directory in which to create the
        virtualenv.
    """
    def run(self):
        check_call(
            ['virtualenv', '--quiet', self.target_path.path],
            env=dict(PYTHONDONTWRITEBYTECODE='1')
        )


@attributes(['virtualenv_path', 'package_uri'])
class InstallApplication(object):
    """
    Install the supplied ``package_uri`` using ``pip`` from the supplied
    ``virtualenv_path``.

    After installing the package and its dependencies, the virtualenv is made
    ``relocatable`` to remove and absolute paths and shebang lines in scripts.

    XXX: The --relocatable option is said to be broken. Investigate using
    ``virtualenv-tools`` instead. See
    https://github.com/jordansissel/fpm/issues/697#issuecomment-48880253 and
    https://github.com/fireteam/virtualenv-tools

    :ivar FilePath virtualenv_path: The path to an existing ``virtualenv``.
    :ivar bytes package_uri: A ``pip install`` compatible package URI.
    """
    def run(self):
        # We can't just call pip directly, because in the virtualenvs created
        # in tests, the shebang line becomes too long and triggers an
        # error. See http://www.in-ulm.de/~mascheck/various/shebang/#errors
        python_path = self.virtualenv_path.child('bin').child('python').path
        pip_path = self.virtualenv_path.child('bin').child('pip').path
        check_call(
            [python_path, pip_path, '--quiet', 'install', self.package_uri]
        )
        check_call(
            ['virtualenv', '--quiet', '--relocatable',
             self.virtualenv_path.path],
            env=dict(PYTHONDONTWRITEBYTECODE='1')
        )

@attributes(['prefix', 'source_path', 'pattern', 'destination_path'])
class CreateLinks(object):
    """
    Create symlinks in ``destination_path`` to the files in ``source_path``
    which match ``pattern``. The links will be absolute paths relative to
    ``prefix``.
    """
    def run(self):
        for child in self.source_path.globChildren(self.pattern):
            absolute_child = FilePath('/').descendant(
                child.segmentsFrom(self.prefix))
            absolute_child.linkTo(
                self.destination_path.child(child.basename()))


@attributes(['virtualenv_path', 'package_name'])
class GetPackageVersion(object):
    """
    Record the version of ``package_name`` installed in ``virtualenv_path`` by
    parsing the output of ``pip show``.

    XXX: This wouldn't be necessary if pip had a way to report the version of
    the package that it is about to install eg
    ``pip install --dry-run http://www.example.com/my/wheel.whl``
    See: https://github.com/pypa/pip/issues/53

    :ivar FilePath virtualenv_path: The path of the ``virtualenv`` containing
        the package.
    :ivar bytes package_name: The name of the package whose version will be
        recorded.
    :ivar version: The version string of the supplied package. Default is
        ``None`` until the step has been run or if the supplied
        ``package_name`` is not found.
    """
    version = None

    def run(self):
        # We can't just call pip directly, because in the virtualenvs created
        # in tests, the shebang line becomes too long and triggers an
        # error. See http://www.in-ulm.de/~mascheck/various/shebang/#errors
        python_path = self.virtualenv_path.child('bin').child('python').path
        pip_path = self.virtualenv_path.child('bin').child('pip').path
        output = check_output(
            [python_path, pip_path, 'show', self.package_name])

        for line in output.splitlines():
            parts = [part.strip() for part in line.split(':', 1)]
            if len(parts) == 2:
                key, value = parts
                if key.lower() == 'version':
                    self.version = value
                    return


@attributes(
    ['destination_path', 'source_path', 'name', 'prefix', 'epoch',
     'rpm_version', 'license', 'url', 'vendor', 'maintainer', 'architecture',
     'description'])
class BuildRpm(object):
    """
    Use ``fpm`` to build an RPM file from the supplied ``source_path``.

    :ivar FilePath destination_path: The path in which to save the resulting
        RPM package file.
    :ivar FilePath source_path: The path to a directory whose contents will be
        packaged.
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
    """
    def run(self):
        architecture = self.architecture
        if architecture is None:
            architecture = 'all'

        depends_arguments = []
        for requirement in FLOCKER_RPM_DEPENDENCIES:
            depends_arguments.extend(['--depends', requirement])

        check_call([
            'fpm',
            '-s', 'dir',
            '-t', 'rpm',
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
            '--exclude', '*.pyc',
            ] + depends_arguments + ['.'], cwd=self.source_path.path
        )


@attributes(['package_version_step'])
class DelayedRpmVersion(object):
    """
    Pretend to be an ``rpm_version`` instance providing a ``version`` and
    ``release`` attribute.

    The values of these attributes will be calculated from the Python version
    string read from a previous ``GetPackageVersion`` build step.

    :ivar GetPackageVersion package_version_step: An instance of
        ``GetPackageVersion`` whose ``run`` method has been called and from
        which the version string will be read.
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


def sumo_rpm_builder(destination_path, package_uri, target_dir=None):
    """
    Build a sequence of build steps which when run will generate an RPM file in
    ``destination_path``, containing the package installed from ``package_uri``
    and all its dependencies.

    The steps are:

    * Create a virtualenv with ``--system-site-packages`` which allows certain
      python libraries to be supplied by the operating system.

    * Install Flocker and all its dependencies in the virtualenv.

    * Find the version of the installed Flocker package, as reported by
      ``pip``.

    * Build an RPM from the virtualenv directory using ``fpm``.

    :param FilePath destination_path: The path to a directory in which to save
        the resulting RPM file.
    :param bytes package_uri: A ``pip install`` compatible package URI.
    :param FilePath target_dir: An optional path in which to create the
        virtualenv from which the package will be generated. Default is a
        temporary directory created using ``mkdtemp``.
    :return: A ``BuildSequence`` instance containing all the required build
        steps.
    """
    if target_dir is None:
        target_dir = FilePath(mkdtemp())
    # Flocker is installed in /opt.
    # See http://fedoraproject.org/wiki/Packaging:Guidelines#Limited_usage_of_.2Fopt.2C_.2Fetc.2Fopt.2C_and_.2Fvar.2Fopt
    virtualenv_dir = target_dir.descendant(['opt', 'flocker'])
    virtualenv_dir.makedirs()

    bin_dir = target_dir.descendant(['usr', 'bin'])
    bin_dir.makedirs()

    get_package_version_step = GetPackageVersion(
        virtualenv_path=virtualenv_dir, package_name='Flocker')

    return BuildSequence(
        steps=(
            InstallVirtualEnv(target_path=virtualenv_dir),
            InstallApplication(virtualenv_path=virtualenv_dir,
                               package_uri=package_uri),
            get_package_version_step,
            CreateLinks(
                prefix=target_dir,
                source_path=virtualenv_dir.child('bin'),
                pattern='flocker-*',
                destination_path=bin_dir
            ),
            BuildRpm(
                destination_path=destination_path,
                source_path=target_dir,
                name='Flocker',
                prefix=FilePath('/'),
                epoch=b'0',
                rpm_version=DelayedRpmVersion(
                    package_version_step=get_package_version_step),
                license='ASL 2.0',
                url='https://clusterhq.com',
                vendor='ClusterHQ',
                maintainer='noreply@build.clusterhq.com',
                architecture='native',
                description=(
                    'A Docker orchestration and volume management tool'),
            )
        )
    )


class BuildOptions(usage.Options):
    """
    Command line options for the ``build-package`` tool.
    """
    synopsis = 'build-rpm [options] <package-uri>'

    optParameters = [
        ['destination-path', 'd', '.',
         'The path to a directory in which to create package files and '
         'artifacts.'],
        ['package-type', 't', 'native',
         'The type of package to build. One of rpm, deb, or native.'],
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
        Coerce to ``FilePath`` where appropriate.
        """
        self['destination-path'] = FilePath(self['destination-path'])


class BuildScript(object):
    """
    Check supplied command line arguments, print command line argument errors
    to ``stderr`` otherwise build the RPM package.

    :ivar build_command: The function responsible for building the
        package. Allows the command to be overridden in tests.
    """
    build_command = staticmethod(sumo_rpm_builder)

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
        options = BuildOptions()

        try:
            options.parseOptions(self.sys_module.argv[1:])
        except usage.UsageError as e:
            self.sys_module.stderr.write("%s\n" % (options,))
            self.sys_module.stderr.write("%s\n" % (e,))
            raise SystemExit(1)

        self.build_command(
            destination_path=options['destination-path'],
            package_uri=options['package-uri']
        ).run()

main = BuildScript().main
