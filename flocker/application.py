"""
The main entry point for the Flocker application.
"""

from __future__ import absolute_import

from zope.interface import implementer

from twisted.application.service import IServiceMaker, MultiService
from twisted.plugin import IPlugin
from twisted.python.usage import Options



class FlockerOptions(Options):
    """
    Command-line options for the Flocker application.
    """



class FlockerService(MultiService):
    """
    The main service for Flocker which runs all other services.
    """



@implementer(IServiceMaker, IPlugin)
class FlockerServiceMaker(object):
    """
    I{twistd} plugin that creates a L{FlockerService}.
    """
    tapname = "flocker"
    description = "The Flocker application."


    def options(self):
        return FlockerOptions()


    def makeService(self, options):
        return FlockerService()


