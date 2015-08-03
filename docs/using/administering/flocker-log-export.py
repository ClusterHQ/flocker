# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A script to export Flocker log files and system information.
"""
import os
from shutil import make_archive, rmtree
from socket import gethostname
from subprocess import check_call, check_output
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

    def _logfile_path(self, name):
        return os.path.join(
            self._archive_name,
            '{}-{}'.format(name, self._suffix)
        )

    def _open_logfile(self, name):
        return open(self._logfile_path(name), 'w')

    def create(self):
        os.makedirs(self._archive_name)
        try:
            for service in self._service_manager.flocker_services():
                self._log_exporter.export_service_logs(
                    service_name=service,
                    export_path=self._logfile_path(service)
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
                base_dir=self._archive_name,
            )
        finally:
            rmtree(self._archive_name)


class CentosServiceManager(object):
    def _parse_units(self, output):
        for line in output.splitlines():
            unit_name, status = line.split()
            if (unit_name.startswith('flocker-') and status == 'enabled'):
                yield unit_name

    def flocker_services(self):
        output = check_output(['systemctl', 'list-unit-files', '--no-legend'])
        return self._parse_units(output)


class CentosLogExporter(object):
    def export_service(self, service_name, target_path):
        check_call(
            'journalctl --all --output cat --unit {unit} '
            '| gzip'.format(service_name),
            stdout=open(target_path, 'w'),
            shell=True
        )

    def export_all(self, target_path):
        check_call(
            'journalctl --all --boot | gzip',
            stdout=open(target_path, 'w'),
            shell=True
        )


def main():
    # Export all logs into a single directory
    service_manager = CentosServiceManager()
    log_exporter = CentosLogExporter()
    FlockerDebugArchive(
        service_manager=service_manager,
        log_exporter=log_exporter
    ).create()


if __name__ == "__main__":
    raise SystemExit(main())
