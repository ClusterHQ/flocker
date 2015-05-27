#!/usr/bin/env python

# This script performs the steps to build the base flocker-tutorial box until
# the box must be rebooted.

from subprocess import check_output

ZFS_REPO_PKG = (
    "https://s3.amazonaws.com/archive.zfsonlinux.org/epel/"
    "zfs-release{dist}.noarch.rpm"
)


def yum_install(*packages):
    check_output(["yum", "install", "-y"] + list(packages))


def main():
    check_output(["yum", "update", "-y"])

    # Install a repository which has ZFS packages.
    dist = check_output(["rpm", "-E", "%dist"]).strip()
    yum_install(ZFS_REPO_PKG.format(dist=dist))

    # Update the kernel and install some development tools necessary for
    # building the ZFS kernel module.
    yum_install("kernel-devel", "kernel", "dkms", "gcc", "make")

    # Install a repository that provides epel packages/updates.
    yum_install("epel-release")

    # The kernel was just upgraded which means the existing VirtualBox Guest
    # Additions will no longer work.  Build them again against the new version
    # of the kernel.
    check_output(["/etc/init.d/vboxadd", "setup"])

    # Create the 'docker' group (???)
    check_output(["groupadd", "docker"])


if __name__ == '__main__':
    main()
