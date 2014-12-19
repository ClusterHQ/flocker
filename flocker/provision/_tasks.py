# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
All the tasks available from the ``task`` directive.
"""

from ._install import (
    task_install_kernel,
    task_install_flocker,
    task_enable_docker,
    task_disable_firewall,
    task_create_flocker_pool_file,
)

__all__ = [
    'task_install_kernel',
    'task_install_flocker',
    'task_enable_docker',
    'task_disable_firewall',
    'task_create_flocker_pool_file',
]
