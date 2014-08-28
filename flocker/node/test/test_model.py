# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._model``.
"""
from twisted.trial.unittest import SynchronousTestCase

from ...testtools import make_with_init_tests
from .._model import Application, DockerImage, Node, Deployment


class DockerImageInitTests(make_with_init_tests(
        record_type=DockerImage,
        kwargs=dict(repository=u'clusterhq/flocker', tag=u'release-14.0'),
        expected_defaults=dict(tag=u'latest')
)):
    """
    Tests for ``DockerImage.__init__``.
    """


class DockerImageTests(SynchronousTestCase):
    """
    Other tests for ``DockerImage``.
    """
    def test_full_name_read(self):
        """
        ``DockerImage.full_name`` combines the repository and tag names in a
        format suitable for passing to `docker run`.
        """
        self.assertEqual(
            'repo:tag', DockerImage(repository=u'repo', tag=u'tag').full_name)

    def test_full_name_write(self):
        """
        ``DockerImage.full_name`` is readonly.
        """
        image = DockerImage(repository=u'repo', tag=u'tag')

        def setter():
            image.full_name = u'foo bar'

        self.assertRaises(AttributeError, setter)

    def test_repr(self):
        """
        ``DockerImage.__repr__`` includes the repository and tag.
        """
        image = DockerImage(repository=u'clusterhq/flocker',
                            tag=u'release-14.0')
        self.assertEqual(
            "<DockerImage(repository=u'clusterhq/flocker', "
            "tag=u'release-14.0')>",
            repr(image)
        )


class DockerImageFromStringTests(SynchronousTestCase):
    """
    Tests for ``DockerImage.from_string``.
    """
    def test_error_on_empty_repository(self):
        """
        A ``ValueError`` is raised if repository is empty.
        """
        exception = self.assertRaises(
            ValueError, DockerImage.from_string, b':foo')
        self.assertEqual(
            "Docker image names must have format 'repository[:tag]'. "
            "Found ':foo'.",
            exception.message
        )


class ApplicationInitTests(make_with_init_tests(
    record_type=Application,
    kwargs=dict(
        name=u'site-example.com', image=object(),
        ports=None, volume=None, environment=None,
        links=frozenset(),
    ),
    expected_defaults={'links': None},
)):
    """
    Tests for ``Application.__init__``.
    """


class ApplicationTests(SynchronousTestCase):
    """
    Other tests for ``Application``.
    """
    def test_repr(self):
        """
        ``Application.__repr__`` includes the name, image, ports, and links.
        """
        application = Application(name=u'site-example.com', image=None,
                                  ports=None, links=frozenset())
        self.assertEqual(
            "<Application(name=u'site-example.com', image=None, ports=None, "
            "volume=None, links=frozenset([]), environment=None)>",
            repr(application)
        )


class NodeInitTests(make_with_init_tests(
        record_type=Node,
        kwargs=dict(hostname=u'example.com', applications=frozenset([
            Application(name=u'mysql-clusterhq', image=object()),
            Application(name=u'site-clusterhq.com', image=object()),
        ]))
)):
    """
    Tests for ``Node.__init__``.
    """


class DeploymentInitTests(make_with_init_tests(
        record_type=Deployment,
        kwargs=dict(nodes=frozenset([
            Node(hostname=u'node1.example.com', applications=frozenset()),
            Node(hostname=u'node2.example.com', applications=frozenset())
        ]))
)):
    """
    Tests for ``Deployment.__init__``.
    """
