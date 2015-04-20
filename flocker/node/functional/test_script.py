# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the agent command line programs.
"""

from ...testtools import make_script_tests


class FlockerZFSAgentTests(make_script_tests(b"flocker-zfs-agent")):
    """
    Tests for ``flocker-zfs-agent``.
    """


class FlockerDatasetAgentTests(make_script_tests(b"flocker-dataset-agent")):
    """
    Tests for ``flocker-dataset-agent``.
    """
