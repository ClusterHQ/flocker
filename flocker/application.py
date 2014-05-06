"""
The main entry point for the Flocker application.
"""

from __future__ import absolute_import

from twisted.application.service import ServiceMaker


class FlockerService(object):
    """
    The main service for Flocker which runs all other services.
    """



class FlockerServiceMaker(ServiceMaker):
    """
    I{twistd} plugin that creates a L{FlockerService}.
    """
    def __init__(self):
        ServiceMaker.__init__(self, "", "", "", "")

