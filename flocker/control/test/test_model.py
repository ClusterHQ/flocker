# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._model``.
"""

from uuid import uuid4

from pyrsistent import InvariantException, pset, PRecord, PSet, pmap

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from ...testtools import make_with_init_tests
from .._model import (
    Application, DockerImage, Node, Deployment, AttachedVolume, Dataset,
    RestartOnFailure, RestartAlways, RestartNever, Manifestation,
    NodeState, pset_field,
)


APP1 = Application(
    name=u"webserver", image=DockerImage.from_string(u"apache"))
APP2 = Application(
    name=u"database", image=DockerImage.from_string(u"postgresql"))
MANIFESTATION = Manifestation(dataset=Dataset(dataset_id=unicode(uuid4())),
                              primary=True)


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
        image = repr(DockerImage(repository=u'clusterhq/flocker',
                                 tag=u'release-14.0'))
        self.assertEqual(
            [image.startswith("DockerImage"),
             "clusterhq/flocker" in image,
             "release-14.0" in image],
            [True, True, True],
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
        name=u'site-example.com', image=DockerImage.from_string(u"image"),
        ports=pset(), volume=None, environment=pmap({}),
        links=pset(), restart_policy=RestartAlways(),
    ),
    expected_defaults={'links': pset(), 'restart_policy': RestartNever()},
)):
    """
    Tests for ``Application.__init__``.
    """


class NodeInitTests(make_with_init_tests(
        record_type=Node,
        kwargs=dict(hostname=u'example.com', applications=pset([
            Application(name=u'mysql-clusterhq', image=DockerImage.from_string(
                u"image")),
            Application(name=u'site-clusterhq.com',
                        image=DockerImage.from_string(u"another")),
        ]))
)):
    """
    Tests for ``Node.__init__``.
    """


class ManifestationTests(SynchronousTestCase):
    """
    Tests for ``Manifestation``.
    """
    def test_dataset_id(self):
        """
        ``Manifestation.dataset_id`` returns the ID of the dataset.
        """
        m1 = Manifestation(dataset=Dataset(dataset_id=unicode(uuid4())),
                           primary=True)
        self.assertEqual(m1.dataset_id, m1.dataset.dataset_id)


class NodeTests(SynchronousTestCase):
    """
    Tests for ``Node``.
    """
    def test_manifestations_from_applications(self):
        """
        One cannot construct a ``Node`` where there are manifestations on the
        ``applications`` attribute that aren't also in the given
        ``manifestations``.
        """
        m1 = Manifestation(dataset=Dataset(dataset_id=unicode(uuid4())),
                           primary=True)
        self.assertRaises(
            InvariantException, Node,
            hostname=u'node1.example.com',
            applications=[
                APP1,
                Application(name=u'a',
                            image=DockerImage.from_string(u'x'),
                            volume=AttachedVolume(
                                manifestation=m1,
                                mountpoint=FilePath(b"/xxx"))),
            ])

    def test_manifestations_non_applications(self):
        """
        ``Node.manifestations`` can include manifestations on the node
        whether or not they are on application.
        """
        m1 = Manifestation(dataset=Dataset(dataset_id=unicode(uuid4())),
                           primary=True)
        m2 = Manifestation(dataset=Dataset(dataset_id=unicode(uuid4())),
                           primary=True)
        node = Node(hostname=u'node1.example.com',
                    applications=frozenset([
                        Application(name=u'a',
                                    image=DockerImage.from_string(u'x'),
                                    volume=AttachedVolume(
                                        manifestation=m1,
                                        mountpoint=FilePath(b"/xxx")))]),
                    manifestations={m1.dataset_id: m1,
                                    m2.dataset_id: m2})

        self.assertEqual(node.manifestations, {m1.dataset_id: m1,
                                               m2.dataset_id: m2})

    def test_applications_contains_applications(self):
        """
        ``Node.applications`` must be ``Application`` instances.
        """
        self.assertRaises(TypeError,
                          Node, hostname=u"xxx", applications=[None])

    def test_manifestations_keys_are_their_ids(self):
        """
        The keys of the ``manifestations`` attribute must match the
        value's ``dataset_id`` attribute.
        """
        self.assertRaises(InvariantException,
                          Node, hostname=u"xxx",
                          manifestations={u"123": MANIFESTATION})


class NodeStateTests(SynchronousTestCase):
    """
    Tests for ``NodeState``.
    """
    def test_running_and_not_running_applications(self):
        """
        ``NodeState.to_node`` combines both running and not running
        applications from the given node state.
        """
        node_state = NodeState(hostname=u"host1",
                               running=[APP1],
                               not_running=[APP2])
        self.assertEqual(node_state.to_node(),
                         Node(hostname=u"host1",
                              applications=frozenset([APP1, APP2])))

    def test_other_manifestations(self):
        """
        ``NodeState.to_node`` copies over other manifestations to the ``Node``
        instances it creates.
        """
        node_state = NodeState(
            hostname=u"host2", running=[], not_running=[],
            manifestations=frozenset([MANIFESTATION]))
        self.assertEqual(node_state.to_node(),
                         Node(hostname=u"host2",
                              applications=frozenset(),
                              manifestations={
                                  MANIFESTATION.dataset.dataset_id:
                                  MANIFESTATION}))


class DeploymentInitTests(make_with_init_tests(
        record_type=Deployment,
        kwargs=dict(nodes=pset([
            Node(hostname=u'node1.example.com', applications=frozenset()),
            Node(hostname=u'node2.example.com', applications=frozenset())
        ]))
)):
    """
    Tests for ``Deployment.__init__``.
    """


class DeploymentTests(SynchronousTestCase):
    """
    Tests for ``Deployment``.
    """
    def test_applications(self):
        """
        ``Deployment.applications()`` returns applications from all nodes.
        """
        node = Node(
            hostname=u"node1.example.com",
            applications=frozenset({
                Application(name=u'mysql-clusterhq',
                            image=DockerImage.from_string(u"image")),
                Application(name=u'site-clusterhq.com',
                            image=DockerImage.from_string(u"image"))}),
        )
        another_node = Node(
            hostname=u"node2.example.com",
            applications=frozenset({Application(
                name=u'site-clusterhq.com',
                image=DockerImage.from_string(u"image"))}),
        )
        deployment = Deployment(nodes=frozenset([node, another_node]))
        self.assertEqual(sorted(list(deployment.applications())),
                         sorted(list(node.applications) +
                                list(another_node.applications)))

    def test_update_node_new(self):
        """
        When doing ``update_node()``, if the given ``Node`` has hostname not
        in existing ``Deployment`` then just add new ``Node`` to new
        ``Deployment``.
        """
        node = Node(
            hostname=u"node1.example.com",
            applications=frozenset({Application(
                name=u'postgresql-clusterhq',
                image=DockerImage.from_string(u"image"))}))
        another_node = Node(
            hostname=u"node2.example.com",
            applications=frozenset({Application(
                name=u'site-clusterhq.com',
                image=DockerImage.from_string(u"image"))}),
        )
        original = Deployment(nodes=frozenset([node]))
        updated = original.update_node(another_node)
        self.assertEqual((original, updated),
                         (Deployment(nodes=frozenset([node])),
                          Deployment(nodes=frozenset([node, another_node]))))

    def test_update_node_replace(self):
        """
        When doing ``update_node()``, if the given ``Node`` has hostname in
        existing ``Deployment`` node then replace that ``Node`` in the new
        ``Deployment``.
        """
        node = Node(
            hostname=u"node1.example.com",
            applications=frozenset({Application(
                name=u'postgresql-clusterhq',
                image=DockerImage.from_string(u"image"))}))
        another_node = Node(
            hostname=u"node2.example.com",
            applications=frozenset({Application(
                name=u'site-clusterhq.com',
                image=DockerImage.from_string(u"image"))}),
        )
        updated_node = Node(
            hostname=u"node1.example.com",
            applications=frozenset())

        original = Deployment(nodes=frozenset([node, another_node]))
        updated = original.update_node(updated_node)
        self.assertEqual((original, updated),
                         (Deployment(nodes=frozenset([node, another_node])),
                          Deployment(nodes=frozenset([
                              updated_node, another_node]))))


class RestartOnFailureTests(SynchronousTestCase):
    """
    Tests for ``RestartOnFailure``.
    """

    def test_maximum_retry_count_not_zero(self):
        """
        ``RestartOnFailure.__init__`` raises ``ValueError`` if the specified
        maximum retry count is 0.
        """
        self.assertRaises(
            InvariantException,
            RestartOnFailure, maximum_retry_count=0)

    def test_maximum_retry_count_not_negative(self):
        """
        ``RestartOnFailure.__init__`` raises ``ValueError`` if the specified
        maximum retry count is negative.
        """
        self.assertRaises(
            InvariantException,
            RestartOnFailure, maximum_retry_count=-1)

    def test_maximum_retry_count_postive(self):
        """
        ``RestartOnFailure.__init__`` does not raise if the specified
        maximum retry count is positive.
        """
        RestartOnFailure(maximum_retry_count=1)

    def test_maximum_retry_count_none(self):
        """
        ``RestartOnFailure.__init__`` does not raise if the specified
        maximum retry count is ``None``.
        """
        RestartOnFailure()

    def test_maximum_retry_count_not_integer(self):
        """
        ``RestartOnFailure.__init__`` raises ``TypeError`` if the supplied
        ``maximum_retry_count`` is not an ``int``
        """
        self.assertRaises(
            InvariantException,
            RestartOnFailure, maximum_retry_count='foo'
        )


class AttachedVolumeTests(SynchronousTestCase):
    """
    Tests for ``AttachedVolume``.
    """
    def test_dataset(self):
        """
        ``AttachedVolume.dataset`` is the same as
        ``AttachedVolume.manifestation.dataset``.
        """
        volume = AttachedVolume(
            manifestation=Manifestation(dataset=Dataset(dataset_id=u"jalkjlk"),
                                        primary=True),
            mountpoint=FilePath(b"/blah"))
        self.assertIs(volume.dataset, volume.manifestation.dataset)


class PSetFieldTests(SynchronousTestCase):
    """
    Tests for ``pset_field``.

    This will hopefully be contributed upstream to pyrsistent, thus the
    slightly different testing style.
    """
    def test_initial_value(self):
        """
        ``pset_field`` results in initial value that is empty.
        """
        class Record(PRecord):
            value = pset_field(int)
        assert Record() == Record(value=[])

    def test_factory(self):
        """
        ``pset_field`` has a factory that creates a ``PSet``.
        """
        class Record(PRecord):
            value = pset_field(int)
        record = Record(value=[1, 2])
        assert isinstance(record.value, PSet)

    def test_checked_set(self):
        """
        ``pset_field`` results in a set that enforces its type.
        """
        class Record(PRecord):
            value = pset_field(int)
        record = Record(value=[1, 2])
        self.assertRaises(TypeError, record.value.add, "hello")

    def test_type(self):
        """
        ``pset_field`` enforces its type.
        """
        class Record(PRecord):
            value = pset_field(int)
        record = Record()
        self.assertRaises(TypeError, record.set, "value", None)

    def test_mandatory(self):
        """
        ``pset_field`` is a mandatory field.
        """
        class Record(PRecord):
            value = pset_field(int)
        record = Record(value=[1])
        self.assertRaises(InvariantException, record.remove, "value")
