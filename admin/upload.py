# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from textwrap import dedent
from admin.runner import run


def add_rpms_to_repository(rpm_directory, target_repo):
    # Create repository metadata for new packages.
    run([b'createrepo', b'--update', rpm_directory.path])

    # Merge with remote metadata.
    run([
        'mergerepo',
        b'--repo', target_repo.replace('gs://',
                                       'https://storage.googleapis.com/'),
        b'--repo', rpm_directory.path,
        # FIXME?: Should this be a seperate directory?
        b'--output', rpm_directory.path])

    # Upload updated repository
    run(
        [b'gsutil', b'cp', b'-R', b'-a', b'public-read',
         rpm_directory.path + b'/*', target_repo])


def download_packages_from_repository(rpm_directory, source_repo, packages):
    # Download requested packages from source repository
    yum_repo_config = rpm_directory.child(b'build.repo')
    yum_repo_config.setContent(dedent(b"""
         [flocker]
         name=flocker
         baseurl=%s
         """) % (source_repo,))
    run([
        b'yumdownloader',
        b'-c', yum_repo_config.path,
        b'--disablerepo=*',
        b'--enablerepo=flocker',
        b'--destdir', rpm_directory.path] + packages)
    yum_repo_config.remove()
