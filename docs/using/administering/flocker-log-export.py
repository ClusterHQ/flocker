# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A script to export Flocker log files and system information.
"""
import os
from shutil import make_archive, rmtree
from socket import gethostname
from subprocess import check_call, check_output
from time import time

SUFFIX = "{}_{}".format(
    gethostname(),
    time()
)
ARCHIVE_NAME = "clusterhq_flocker_logs_{}".format(SUFFIX)


def parse_units(output):
    for line in output.splitlines():
        unit_name, status = line.split()
        if (unit_name.startswith('flocker-') and status == 'enabled'):
            yield unit_name


def flocker_units():
    output = check_output(['systemctl', 'list-unit-files', '--no-legend'])
    return parse_units(output)


def open_logfile(name):
    logfile_path = os.path.join(ARCHIVE_NAME, '{}-{}'.format(name, SUFFIX))
    return open(logfile_path, 'w')


def main():
    # Export all logs into a single directory
    os.makedirs(ARCHIVE_NAME)
    try:
        for unit in flocker_units():
            check_call(
                'journalctl --all --output cat --unit {unit} '
                '| gzip'.format(unit),
                stdout=open_logfile(unit),
                shell=True
            )

        # Export the full journal since last boot
        check_call(
            'journalctl --all --boot | gzip',
            stdout=open_logfile('all'),
            shell=True
        )

        # Export Docker version and configuration
        check_call(['docker', 'info'], stdout=open_logfile('docker_info'))
        check_call(
            ['docker', 'version'],
            stdout=open_logfile('docker_version')
        )

        # Kernel version
        open_logfile('uname').write(' '.join(os.uname()))

        # Distribution version
        open_logfile('os-release').write(open('/etc/os-release').read())

        # Create a single archive file
        make_archive(
            base_name=ARCHIVE_NAME,
            format='tar',
            base_dir=ARCHIVE_NAME,
        )
    finally:
        rmtree(ARCHIVE_NAME)

if __name__ == "__main__":
    raise SystemExit(main())
