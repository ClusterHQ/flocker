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
    * https://github.com/opscode/omnibus (Package Ruby apps with their dependencies)
    * https://github.com/bernd/fpm-cookery
    * http://dh-virtualenv.readthedocs.org/en/latest/info.html
    * https://github.com/mozilla/socorro/blob/master/scripts/install.sh and
      https://github.com/mozilla/socorro/blob/master/scripts/package.sh and
      http://socorro.readthedocs.org/en/latest/installation/install-src-prod.html

    TODO:
    * Build fpm platform packages for quicker installation on build slaves
      https://github.com/hatt/omnibus-fpm
    *
"""
import platform
import sys
from subprocess import check_output, check_call
from tempfile import mkdtemp
from textwrap import dedent


from twisted.python.constants import ValueConstant, Values
from twisted.python.filepath import FilePath
from twisted.python import usage, log

from characteristic import attributes, Attribute
import virtualenv

from .release import make_rpm_version


class PackageTypes(Values):
    RPM = ValueConstant('rpm')
    DEB = ValueConstant('deb')


# Associate package formats with platform operating systems.
PACKAGE_TYPE_MAP = {
    PackageTypes.RPM: ('fedora', 'centos'),
    PackageTypes.DEB: ('ubuntu',),
}


@attributes(['name', 'version'])
class Distribution(object):
    """
    A linux distribution.

    :ivar bytes name: The name of the distribution.
    :ivar bytes version: The version of the distribution.
    """

    @classmethod
    def _get_current_distribution(klass):
        name, version, id = (
            platform.linux_distribution(full_distribution_name=False))
        return klass(name=name.lower(), version=version)


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


def run_command(args, env=None, cwd=None):
    log.msg(
        format="Running %(args)r with environment %(env)r "
               "and working directory %(cwd)s",
        args=args, env=env, cwd=cwd)
    return check_output(
        args=args,
        env=env,
        cwd=cwd,
    )


@attributes([
    Attribute('package'),
    Attribute('compare', default_value=None),
    Attribute('version', default_value=None)])
class Dependency(object):
    """
    Package dependency
    """
    def __init__(self):
        if (self.compare is None) != (self.version is None):
            raise ValueError(
                "Must specify both or neither compare and version.")

    def format(self, package_type):
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
            Dependency(package='docker-io', compare='>=', version='1.2'),
            Dependency(package='/usr/sbin/iptables'),
            Dependency(package='zfs', compare='>=', version='0.6.3'),
            Dependency(package='openssh-clients'),
        ),
        'centos': (
            Dependency(package='docker', compare='>=', version='1.2'),
            Dependency(package='/usr/sbin/iptables'),
            Dependency(package='zfs', compare='>=', version='0.6.3'),
            Dependency(package='openssh-clients'),
        ),
        'ubuntu': (
            # trust-updates version
            Dependency(package='docker.io', compare='>=', version='1.0.1'),
            Dependency(package='iptables'),
            Dependency(package='zfsutils', compare='>=', version='0.6.3'),
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
        env=dict(PYTHONDONTWRITEBYTECODE='1')
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
    :ivar bytes name: The name of the package.
    :ivar bytes version: The version of the package.
    """


@attributes(['root'])
class VirtualEnv(object):
    """
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
    Install the supplied ``package`` using the supplied ``virtualenv``.

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
    parsing the output of ``pip show``.

    XXX: This wouldn't be necessary if pip had a way to report the version of
    the package that it is about to install eg
    ``pip install --dry-run http://www.example.com/my/wheel.whl``
    See: https://github.com/pypa/pip/issues/53

    :ivar VirtualEnv virtualenv: The ``virtualenv`` containing the package.
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
        python_path = self.virtualenv.root.child('bin').child('python').path
        output = check_output(
            [python_path, '-m', 'pip', 'show', self.package_name])

        for line in output.splitlines():
            parts = [part.strip() for part in line.split(':', 1)]
            if len(parts) == 2:
                key, value = parts
                if key.lower() == 'version':
                    self.version = value
                    return


@attributes(
    ['package_type', 'destination_path', 'source_paths', 'name', 'prefix',
     'epoch', 'rpm_version', 'license', 'url', 'vendor', 'maintainer',
     'architecture', 'description', 'dependencies',
     Attribute('after_install', default_value=None)])
class BuildPackage(object):
    """
    Use ``fpm`` to build an RPM file from the supplied ``source_path``.

    :ivar FilePath destination_path: The path in which to save the resulting
        RPM package file.
    :ivar dict source_paths: A dictionary mapping paths in the filesystem to the
        path in the package.
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
    :ivar list dependencies: The list of dependencies of the package.
    """
    def run(self):
        architecture = self.architecture

        depends_arguments = []
        for requirement in self.dependencies:
            depends_arguments.extend(['--depends', requirement.format(self.package_type)])

        if self.after_install is not None:
            depends_arguments.extend(
                ['--after-install', self.after_install.path]
            )

        path_arguments = []
        for source_path, package_path in self.source_paths.items():
            # Think of /= as a separate operator. It causes fpm to copy the
            # content of the directory rather than the directory its self.
            path_arguments.append("%s/=%s" % (source_path.path, package_path.path))

        run_command([
            'fpm',
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
            ] + depends_arguments + path_arguments
        )


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


class PACKAGE(Values):
    EPOCH = ValueConstant(b'0')
    LICENSE = ValueConstant(b'ASL 2.0')
    URL = ValueConstant(b'https://clusterhq.com')
    VENDOR = ValueConstant(b'ClusterHQ')
    MAINTAINER = ValueConstant(b'noreply@build.clusterhq.com')


def sumo_package_builder(
        package_type, destination_path, package_uri, target_dir=None):
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
    # See http://fedoraproject.org/wiki/Packaging:Guidelines#Limited_usage_of_.2Fopt.2C_.2Fetc.2Fopt.2C_and_.2Fvar.2Fopt
    virtualenv_dir = FilePath('/opt/flocker')

    virtualenv = VirtualEnv(root=virtualenv_dir)

    get_package_version_step = GetPackageVersion(
        virtualenv=virtualenv, package_name='Flocker')
    rpm_version = DelayedRpmVersion(
        package_version_step=get_package_version_step)


    return BuildSequence(
        steps=(
            InstallVirtualEnv(virtualenv=virtualenv),
            InstallApplication(virtualenv=virtualenv,
                               package_uri=package_uri),
            # get_package_version_step must be run before steps that reference
            # rpm_version
            get_package_version_step,
            BuildPackage(
                package_type=package_type,
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
                description=(
                    'A Docker orchestration and volume management tool'),
                dependencies=DEPENDENCIES['python'][CURRENT_DISTRIBUTION.name],
            ),

            # flocker-cli steps
            CreateLinks(
                links=[
                    (FilePath('/opt/flocker/bin/flocker-deploy'),
                     flocker_cli_path),
                ]
            ),
            BuildPackage(
                package_type=package_type,
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
                description=(
                    'A Docker orchestration and volume management tool'),
                dependencies=DEPENDENCIES['cli'][CURRENT_DISTRIBUTION.name],
            ),
            # flocker-node steps
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
                package_type=package_type,
                destination_path=destination_path,
                source_paths={flocker_node_path: FilePath("/usr/sbin")},
                name='clusterhq-flocker-node',
                prefix=FilePath('/'),
                epoch=PACKAGE.EPOCH.value,
                rpm_version=rpm_version,
                license=PACKAGE.LICENSE.value,
                url=PACKAGE.URL.value,
                vendor=PACKAGE.VENDOR.value,
                maintainer=PACKAGE.MAINTAINER.value,
                architecture='all',
                description=(
                    'A Docker orchestration and volume management tool'),
                dependencies=DEPENDENCIES['node'][CURRENT_DISTRIBUTION.name],
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
            ['docker', 'build', '--tag', self.tag, self.build_directory])


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
            volume_options.extend(['--volume', '%s:%s' % (host.path, container.path)])

        check_call(['docker', 'run',] + volume_options +  [self.tag] + self.command)


def build_package(destination_path, distribution, top_level, package_uri):
    """
    Build a flocker package for a given ``distribution`` inside a clean docker
    container of that ``distribution``.

    :param FilePath destination_path: The directory to which the generated
         packages will be copied.
    :param bytes distribution: The distribution name for which to build a
        package.
    :param bytes package_uri: The ``pip`` style python package URI to install.
    """
    if destination_path.exists() and not destination_path.isdir():
        raise ValueError("go away")
    #destination_path.makedirs()

    tag = "clusterhq/build_%s" % (distribution,)
    build_directory = top_level.descendant(['admin', 'build_targets', distribution])

    return BuildSequence(
        steps=[
            DockerBuild(
                tag=tag,
                build_directory=build_directory.path
            ),
            DockerRun(
                tag=tag,
                volumes={
                    FilePath('/output'): destination_path,
                    FilePath('/flocker'): top_level,
                },
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
        Coerce paths to ``FilePath`` and select a suitable ``native``
        ``package-type``.
        """
        self['destination-path'] = FilePath(self['destination-path'])
        if self['package-type'] == 'native':
            self['package-type'] = _native_package_type()
        else:
            self['package-type'] = PackageTypes.lookupByValue(self['package-type'])


class DockerBuildScript(object):
    """
    Check supplied command line arguments, print command line argument errors
    to ``stderr`` otherwise build the RPM package.

    :ivar build_command: The function responsible for building the
        package. Allows the command to be overridden in tests.
    """
    build_command = staticmethod(sumo_package_builder)

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
            package_type=options['package-type'],
            destination_path=options['destination-path'],
            package_uri=options['package-uri'],
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
         'The target distribution. One of fedora20, centos7, or ubuntu1404.'],
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
        if self['distribution'] == None:
            raise usage.UsageError('Must specify --distribution.')


class BuildScript(object):
    """
    Check supplied command line arguments, print command line argument errors
    to ``stderr`` otherwise build the RPM package.

    :ivar build_command: The function responsible for building the
        package. Allows the command to be overridden in tests.
    """
    build_command = staticmethod(build_package)

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
