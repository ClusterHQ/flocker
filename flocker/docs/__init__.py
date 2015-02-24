# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Sphinx extensions for flocker.
Components for Flocker documentation.
"""

from ._version import (
    get_doc_version, get_installable_version,
    is_release, is_weekly_release,
)

__all__ = [
    'get_doc_version', 'get_installable_version',
    'is_release', 'is_weekly_release',
]
