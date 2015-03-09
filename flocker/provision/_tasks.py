# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
All the tasks available from the ``task`` directive.
"""

from ._install import (
    task_create_flocker_pool_file,
    task_disable_firewall,
    task_enable_docker,
    task_install_flocker,
    task_install_kernel_devel,
    task_install_ssh_key,
    task_upgrade_kernel,
    task_upgrade_selinux,
    task_open_control_firewall,
)

__all__ = [
    'task_create_flocker_pool_file',
    'task_disable_firewall',
    'task_enable_docker',
    'task_install_flocker',
    'task_install_kernel_devel',
    'task_install_ssh_key',
    'task_upgrade_kernel',
    'task_upgrade_selinux',
    'task_open_control_firewall',
]
