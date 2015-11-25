import json
import platform
from unittest import skipIf

from twisted.trial.unittest import SynchronousTestCase

from flocker.node.diagnostics import list_hardware

on_linux = skipIf(platform.system() != 'Linux', 'Requires Linux')


class ListHardwareTests(SynchronousTestCase):

    @on_linux
    def test_list_hardware(self):
        """
        ``list_hardware`` returns valid JSON.
        """
        json.loads(list_hardware())

    @on_linux
    def test_list_hardware_classes(self):
        """
        ``list_hardware`` with classes only provides named classes.
        """
        processors = json.loads(list_hardware(['processor']))
        self.assertEqual(
            set(processor['class'] for processor in processors),
            {'processor'}
        )
