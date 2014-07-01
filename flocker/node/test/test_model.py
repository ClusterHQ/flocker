# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._model``.
"""


from ...testtools import make_with_init_tests
from .._model import Application, DockerImage

class DockerImageInitTests(make_with_init_tests(
    record_type=DockerImage,
    kwargs=dict(repository=u'clusterhq/flocker', tag=u'release-14.0')
)):
    """
    Tests for ``DockerImage.__init__``.
    """


class ApplicationInitTests(make_with_init_tests(
    record_type=Application,
    kwargs=dict(name=u'site-example.com', image=object())
)):
    """
    Tests for ``Application.__init__``.
    """
