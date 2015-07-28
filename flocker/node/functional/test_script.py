# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the agent command line programs.
"""
from zope.interface import implementer
from twisted.trial.unittest import TestCase
from ...testtools import make_script_tests, run_process
from ..script import IFlockerLogExporter


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


class IFlockerLogExporterTestsMixin(object):
    """
    """
    def test_interface(self):
        """
        ``exporter`` provides ````IFlockerLogExporter``.
        """

    def test_export(self):
        """
        ``exporter.export`` writes to output_file.
        """
        1/0


def make_iflockerlogexporter_tests(log_exporter):
    class Tests(IFlockerLogExporterTestsMixin, TestCase):
        def setUp(self):
            self.exporter = log_exporter()

    return Tests


@implementer(IFlockerLogExporter)
class UbuntuLogExporter(object):
    """
    """


class IFlockerLogExporterUpstartTests(
    make_iflockerlogexporter_tests(log_exporter=UbuntuLogExporter)
):
    """
    Tests for ``IFlockerLogExporter`` with ``Upstart``.
    """
