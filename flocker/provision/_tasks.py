# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
All the tasks available from the ``task`` directive.
"""

from ._install import (
    task_create_flocker_pool_file,
    task_disable_selinux,
    task_enable_docker,
    task_install_flocker,
    task_install_ssh_key,
    task_install_cli,
    task_test_homebrew,
    task_upgrade_kernel,
    task_configure_flocker_agent,
    task_enable_flocker_control,
    task_enable_flocker_agent,
    task_open_control_firewall,
    task_install_zfs,
)

__all__ = [
    'task_create_flocker_pool_file',
    'task_disable_selinux',
    'task_enable_docker',
    'task_install_flocker',
    'task_install_ssh_key',
    'task_install_cli',
    'task_test_homebrew',
    'task_upgrade_kernel',
    'task_configure_flocker_agent',
    'task_enable_flocker_control',
    'task_enable_flocker_agent',
    'task_open_control_firewall',
    'task_install_zfs',
]
