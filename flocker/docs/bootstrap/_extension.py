# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Bootstrap extension entry point.
"""

from . import _simple, _tabs


def setup(app):
    """
    Entry point for sphinx extension.
    """

    for module in [_simple, _tabs]:
        module.setup(app)
