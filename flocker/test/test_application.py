"""
Tests for L{flocker.application} and L{twistd} support.
"""

from __future__ import absolute_import

from twisted.trial.unittest import TestCase
from twisted.application.service import IServiceMaker, IServiceCollection
from twisted.plugin import getPlugins
from zope.interface.verify import verifyObject

from ..application import FlockerServiceMaker, FlockerService, FlockerOptions


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
        self.assertTrue(verifyObject(IServiceMaker, FlockerServiceMaker()))


    def test_name(self):
        """
        L{FlockerServiceMaker.tapname} is C{"flocker"}.
        """
        maker = FlockerServiceMaker()
        self.assertEqual(maker.tapname, "flocker")


    def test_options(self):
        """
        L{FlockerServiceMaker.options} returns a L{Options} instance.
        """
        maker = FlockerServiceMaker()
        options = maker.options()
        self.assertIsInstance(options, FlockerOptions)


    def test_makeService(self):
        """
        L{FlockerServiceMaker.makeService} creates a L{FlockerService} instance.
        """
        maker = FlockerServiceMaker()
        service = maker.makeService(maker.options())
        self.assertIsInstance(service, FlockerService)



class FlockerServiceTests(TestCase):
    """
    Tests for L{FlockerService}.
    """
    def test_interface(self):
        """
        L{FlockerService} implements L{IServiceCollection}.
        """
        self.assertTrue(verifyObject(IServiceCollection, FlockerService()))
