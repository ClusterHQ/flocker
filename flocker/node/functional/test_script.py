# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the agent command line programs.
"""
from ...testtools import make_script_tests, run_process
from ..testtools import make_iflockerlogexporter_tests
from ..script import UpstartLogExporter, JournalDLogExporter


class FlockerDatasetAgentTests(make_script_tests(b"flocker-dataset-agent")):
    """
    Tests for ``flocker-dataset-agent``.
    """


class FlockerContainerAgentTests(
        make_script_tests(b"flocker-container-agent")):
    """
    Tests for ``flocker-container-agent``.
    """


class FlockerLogExportTests(
        make_script_tests(b"flocker-log-export")):
    """
    Tests for ``flocker-log-export``.
    """
    def test_export_all(self):
        """
        """
        result = run_process(
            [self.executable] + [b'--platform=upstart']
        )
        self.assertEqual('', result.output)


class IFlockerLogExporterUpstartTests(
    make_iflockerlogexporter_tests(log_exporter=UpstartLogExporter)
):
    """
    Tests for ``IFlockerLogExporter`` with ``Upstart``.
    """


class IFlockerLogExporterJournaldTests(
    make_iflockerlogexporter_tests(log_exporter=JournalDLogExporter)
):
    """
    Tests for ``IFlockerLogExporter`` with ``Upstart``.
    """
