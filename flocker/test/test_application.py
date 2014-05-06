"""
Tests for L{flocker.application} and L{twistd} support.
"""

from __future__ import absolute_import

from twisted.trial.unittest import TestCase
from twisted.application.service import IServiceMaker
from twisted.plugin import getPlugins

from zope.interface.verify import verifyClass

from ..application import FlockerServiceMaker


class FlockerServiceMakerTests(TestCase):
    """
    Tests for L{FlockerServiceMaker} and the L{twistd} plugin support it
    provides.
    """
    def test_plugin(self):
        """
        A L{FlockerServiceMaker} instance is registered as a twistd plugin.
        """
        plugins = getPlugins(IServiceMaker)
        self.assertIn(FlockerServiceMaker,
                      [plugin.__class__ for plugin in plugins])


    def test_interface(self):
        """
        L{FlockerServiceMaker} implements L{IServiceMaker}.
        """
        self.assertTrue(verifyClass(IServiceMaker, FlockerServiceMaker))
