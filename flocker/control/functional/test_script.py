"""
Functional tests for ``flocker.control.script``.
"""

from ...testtools import make_script_tests


class FlockerControlTests(make_script_tests(b"flocker-control")):
    """
    Tests for ``flocker-control``.
    """
