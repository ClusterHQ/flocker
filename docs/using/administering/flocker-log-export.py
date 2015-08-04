# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A script to export Flocker log files and system information.
"""
from gzip import open as gzip_open
import os
import platform
import re
from shutil import copyfileobj, make_archive, rmtree
from socket import gethostname
from subprocess import check_call, check_output
from tarfile import open as tarfile_open
from time import time


class FlockerDebugArchive(object):
    """
    """
    def __init__(self, service_manager, log_exporter):
        self._service_manager = service_manager
        self._log_exporter = log_exporter

        self._suffix = "{}_{}".format(
            gethostname(),
            time()
        )
        self._archive_name = "clusterhq_flocker_logs_{}".format(
            self._suffix
        )
        self._archive_path = os.path.abspath(self._archive_name)

    def _logfile_path(self, name):
        return os.path.join(
            self._archive_name,
            '{}-{}'.format(name, self._suffix)
        )

    def _open_logfile(self, name):
        return open(self._logfile_path(name), 'w')

    def create(self):
        os.makedirs(self._archive_path)
        try:
            for service in self._service_manager.flocker_services():
                self._log_exporter.export_service(
                    service_name=service,
                    target_path=self._logfile_path(service)
                )
            self._log_exporter.export_all(self._logfile_path('all'))
            # Export Docker version and configuration
            check_call(
                ['docker', 'info'],
                stdout=self._open_logfile('docker_info')
            )
            check_call(
                ['docker', 'version'],
                stdout=self._open_logfile('docker_version')
            )

            # Kernel version
            self._open_logfile('uname').write(' '.join(os.uname()))

            # Distribution version
            self._open_logfile('os-release').write(
                open('/etc/os-release').read()
            )
            # Create a single archive file
            make_archive(
                base_name=self._archive_name,
                format='tar',
                root_dir=os.path.dirname(self._archive_path),
                base_dir=os.path.basename(self._archive_path),
            )
        finally:
            rmtree(self._archive_path)


class SystemdServiceManager(object):
    def _parse_units(self, output):
        for line in output.splitlines():
            unit_name, status = line.split()
            if (unit_name.startswith('flocker-') and status == 'enabled'):
                yield unit_name

    def flocker_services(self):
        output = check_output(['systemctl', 'list-unit-files', '--no-legend'])
        return self._parse_units(output)


class UpstartServiceManager(object):
    def flocker_services(self):
        for childname in os.listdir('/var/log/upstart'):
            match = re.match(r'^(flocker-.+)\.log', childname)
            if match:
                [service_name] = match.groups(1)
                yield service_name


class JournaldLogExporter(object):
    def export_service(self, service_name, target_path):
        check_call(
            'journalctl --all --output cat --unit {unit} '
            '| gzip'.format(service_name),
            stdout=open(target_path + '.gz', 'w'),
            shell=True
        )

    def export_all(self, target_path):
        check_call(
            'journalctl --all --boot | gzip',
            stdout=open(target_path + '.gz', 'w'),
            shell=True
        )


class UpstartLogExporter(object):
    def export_service(self, service_name, target_path):
        with tarfile_open(target_path + '.tar.gz', 'w|gz') as tar:
            files = [
                ("/var/log/upstart/{}.log".format(service_name), service_name + '-upstart.log'),
                ("/var/log/flocker/{}.log".format(service_name), service_name + '-eliot.log'),
            ]
            for input_path, archive_name in files:
                if os.path.isfile(input_path):
                    tar.add(input_path, arcname=archive_name)

    def export_all(self, target_path):
        with open('/var/log/syslog', 'rb') as f_in, gzip_open(target_path + '.gz', 'wb') as f_out:
            copyfileobj(f_in, f_out)

class Platform(object):
    def __init__(self, name, version, service_manager, log_exporter):
        self.name = name
        self.version = version
        self.service_manager = service_manager
        self.log_exporter = log_exporter


PLATFORMS = (
    Platform(
        name='centos',
        version='7',
        service_manager=SystemdServiceManager(),
        log_exporter=JournaldLogExporter()
    ),
    Platform(
        name='fedora',
        version='22',
        service_manager=SystemdServiceManager(),
        log_exporter=JournaldLogExporter()
    ),
    Platform(
        name='ubuntu',
        version='14.04',
        service_manager=UpstartServiceManager(),
        log_exporter=UpstartLogExporter()
    )
)


_PLATFORM_BY_LABEL = dict(
    ('{}-{}'.format(p.name, p.version), p)
    for p in PLATFORMS
)


def current_platform():
    name, version, nickname = platform.dist()
    return _PLATFORM_BY_LABEL[name.lower() + '-' + version]


def main():
    # Export all logs into a single directory
    platform = current_platform()
    FlockerDebugArchive(
        service_manager=platform.service_manager,
        log_exporter=platform.log_exporter
    ).create()


if __name__ == "__main__":
    raise SystemExit(main())
