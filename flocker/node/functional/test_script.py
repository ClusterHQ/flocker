# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the agent command line programs.
"""

from ...testtools import make_script_tests


class FlockerDatasetAgentTests(make_script_tests(b"flocker-dataset-agent")):
    """
    Tests for ``flocker-dataset-agent``.
    """


class FlockerContainerAgentTests(
        make_script_tests(b"flocker-container-agent")):
    """
    Tests for ``flocker-container-agent``.
    """
