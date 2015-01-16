# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Bootstrap extension entry point.
"""

from . import _jumbotron, _logo, _columns


def setup(app):
    """
    Entry point for sphinx extension.
    """

    for module in [_jumbotron, _logo, _columns]:
        module.setup(app)
