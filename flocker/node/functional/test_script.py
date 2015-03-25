# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-changestate`` command line tool.
"""

from ...testtools import make_script_tests


class FlockerChangeStateTests(make_script_tests(b"flocker-changestate")):
    """
    Tests for ``flocker-changestate``.
    """


class FlockerReportStateTests(make_script_tests(b"flocker-reportstate")):
    """
    Tests for ``flocker-reportstate``.
    """


class FlockerZFSAgentTests(make_script_tests(b"flocker-zfs-agent")):
    """
    Tests for ``flocker-zfs-agent``.
    """


class FlockerDatasetAgentTests(make_script_tests(b"flocker-dataset-agent")):
    """
    Tests for ``flocker-dataset-agent``.
    """
