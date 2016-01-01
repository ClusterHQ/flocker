import json
from unittest import skipUnless

from twisted.python.procutils import which

from flocker.node.diagnostics import list_hardware
from flocker.testtools import TestCase


class ListHardwareTests(TestCase):

    @skipUnless(which('lshw'), 'Tests require the ``lshw`` command.')
    def test_list_hardware(self):
        """
        ``list_hardware`` returns valid JSON.
        """
        json.loads(list_hardware())

    @skipUnless(which('lshw'), 'Tests require the ``lshw`` command.')
    def test_list_hardware_classes(self):
        """
        ``list_hardware`` with classes only provides named classes.
        """
        processors = json.loads(list_hardware(['processor']))
        self.assertEqual(
            set(processor['class'] for processor in processors),
            {'processor'}
        )
