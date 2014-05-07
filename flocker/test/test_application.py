"""
Tests for :module:`flocker.application` and ``twistd`` support.
"""

from __future__ import absolute_import

from twisted.trial.unittest import TestCase
from twisted.application.service import IServiceMaker, IServiceCollection
from twisted.plugin import getPlugins
from zope.interface.verify import verifyObject

from ..application import FlockerServiceMaker, FlockerService, FlockerOptions


class FlockerServiceMakerTests(TestCase):
    """
    Tests for :class:`FlockerServiceMaker` and the ``twistd`` plugin support it
    provides.
    """
    def test_plugin(self):
        """
        A :class:`FlockerServiceMaker` instance is registered as a twistd
        plugin.
        """
        plugins = getPlugins(IServiceMaker)
        self.assertIn(FlockerServiceMaker,
                      [plugin.__class__ for plugin in plugins])


    def test_interface(self):
        """
        :class:`FlockerServiceMaker` implements :class:`IServiceMaker`.
        """
        self.assertTrue(verifyObject(IServiceMaker, FlockerServiceMaker()))


    def test_name(self):
        """
        :class:`FlockerServiceMaker.tapname` is C{"flocker"`.
        """
        maker = FlockerServiceMaker()
        self.assertEqual(maker.tapname, "flocker")


    def test_options(self):
        """
        :class:`FlockerServiceMaker.options` returns a :class:`Options`
        instance.
        """
        maker = FlockerServiceMaker()
        options = maker.options()
        self.assertIsInstance(options, FlockerOptions)


    def test_makeService(self):
        """
        :class:`FlockerServiceMaker.makeService` creates a
        :class:`FlockerService` instance.
        """
        maker = FlockerServiceMaker()
        service = maker.makeService(maker.options())
        self.assertIsInstance(service, FlockerService)



class FlockerServiceTests(TestCase):
    """
    Tests for :class:`FlockerService`.
    """
    def test_interface(self):
        """
        :class:`FlockerService` implements :class:`IServiceCollection`.
        """
        self.assertTrue(verifyObject(IServiceCollection, FlockerService()))
