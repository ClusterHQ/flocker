# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
All the tasks available from the ``task`` directive.
"""

from ._install import (
    task_create_flocker_pool_file,
    task_enable_docker,
    task_install_flocker,
    task_install_digitalocean_kernel,
    task_install_aws_fedora20_kernel,
    task_install_kernel_devel,
    task_install_ssh_key,
    task_test_homebrew,
    task_upgrade_kernel_centos,
    task_upgrade_selinux,
    task_enable_flocker_control,
    task_enable_flocker_agent,
    task_open_control_firewall,
)

__all__ = [
    'task_create_flocker_pool_file',
    'task_enable_docker',
    'task_install_flocker',
    'task_install_digitalocean_kernel',
    'task_install_aws_fedora20_kernel',
    'task_install_kernel_devel',
    'task_install_ssh_key',
    'task_test_homebrew',
    'task_upgrade_kernel_centos',
    'task_upgrade_selinux',
    'task_enable_flocker_control',
    'task_enable_flocker_agent',
    'task_open_control_firewall',
]
