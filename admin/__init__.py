# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Admin scripts and modules which should not be shipped with Flocker.
"""

from ._release import make_rpm_version, rpm_version

__all__ = ['make_rpm_version', 'rpm_version']
