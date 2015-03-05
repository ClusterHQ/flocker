# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.route._model``.
"""

from ipaddr import IPAddress

from .._model import Proxy, Port

from ...testtools import make_with_init_tests


class ProxyInitTests(make_with_init_tests(
        record_type=Proxy,
        kwargs=dict(ip=IPAddress("10.0.1.2"), port=12345))):
    """
    Tests for ``Proxy.__init__``.
    """


class PortInitTests(make_with_init_tests(
        record_type=Port,
        kwargs=dict(port=12345))):
    """
    Tests for ``Port.__init__``.
    """
