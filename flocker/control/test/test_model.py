# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._model``.
"""

from uuid import uuid4

from pyrsistent import (
    InvariantException, pset, PRecord, PSet, pmap, PMap, thaw
)

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from zope.interface.verify import verifyObject

from ...testtools import make_with_init_tests
from .._model import pset_field, pmap_field
from .. import (
    IClusterStateChange,
    Application, DockerImage, Node, Deployment, AttachedVolume, Dataset,
    RestartOnFailure, RestartAlways, RestartNever, Manifestation,
    NodeState, DeploymentState, NonManifestDatasets,
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
    def test_iclusterstatechange(self):
        """
        ``NodeState`` instances provide ``IClusterStateChange``.
        """
        self.assertTrue(
            verifyObject(IClusterStateChange, NodeState(hostname=u"1.2.3.4"))
        )

    def test_update_cluster_state(self):
        """
        ``NodeState.update_cluster_state`` returns a new ``DeploymentState``
        with the state of the ``NodeState`` with the matching ``hostname``
        replaced with its own state.
        """
        hostname = u"1.2.3.4"
        apps = {APP1}
        manifestations = {MANIFESTATION.dataset_id: MANIFESTATION}
        node = NodeState(
            hostname=hostname,
            applications=None,
            manifestations=None,
        )
        app_state = node.set(applications=apps)
        data_state = node.set(manifestations=manifestations)
        cluster = DeploymentState(nodes={app_state})
        changed_cluster = data_state.update_cluster_state(cluster)
        self.assertEqual(
            DeploymentState(nodes={
                NodeState(
                    hostname=hostname,
                    applications=apps,
                    manifestations=manifestations,
                )
            }),
            changed_cluster
        )

    def test_manifestations_keys_are_their_ids(self):
        """
        The keys of the ``manifestations`` attribute must match the
        value's ``dataset_id`` attribute.
        """
        self.assertRaises(InvariantException,
                          NodeState, hostname=u"xxx",
                          manifestations={u"123": MANIFESTATION})

    def test_no_manifestations(self):
        """
        A ``NodeState`` may have ``manifestations`` set to ``None``, indicating
        ignorance of the correct value.
        """
        self.assertEqual(
            NodeState(hostname=u"1.2.3.4", manifestations=None).manifestations,
            None)

    def test_no_applications(self):
        """
        A ``NodeState`` may have ``applications`` set to ``None``, indicating
        ignorance of the correct value.
        """
        self.assertEqual(
            NodeState(hostname=u"1.2.3.4", applications=None).applications,
            None)

    def test_no_paths(self):
        """
        A ``NodeState`` may have ``paths`` set to ``None``, indicating
        ignorance of the correct value.
        """
        self.assertEqual(
            NodeState(hostname=u"1.2.3.4", paths=None).paths,
            None)

    def test_no_used_ports(self):
        """
        A ``NodeState`` may have ``used_ports`` set to ``None``, indicating
        ignorance of the correct value.
        """
        self.assertEqual(
            NodeState(hostname=u"1.2.3.4", used_ports=None).used_ports,
            None)


class NonManifestDatasetsInitTests(make_with_init_tests(
        record_type=NonManifestDatasets,
        kwargs=dict(datasets={
            MANIFESTATION.dataset.dataset_id: MANIFESTATION.dataset,
        })
)):
    """
    Tests for ``NonManifestDatasets.__init__``.
    """


class NonManifestDatasetsTests(SynchronousTestCase):
    """
    Tests for ``NonManifestDatasets``.
    """
    def test_iclusterstatechange(self):
        """
        ``NonManifestDatasets`` instances provide ``IClusterStateChange``.
        """
        self.assertTrue(
            verifyObject(IClusterStateChange, NonManifestDatasets())
        )

    def test_manifestations_keys_are_their_ids(self):
        """
        The keys of the ``datasets`` attribute must match the value's
        ``dataset_id`` attribute.
        """
        self.assertRaises(
            InvariantException,
            NonManifestDatasets,
            datasets={unicode(uuid4()): Dataset(dataset_id=unicode(uuid4()))},
        )

    def test_update_cluster_state(self):
        """
        ``NonManifestDatasets.update_cluster_state`` returns a new
        ``DeploymentState`` instance with its ``nonmanifest_datasets`` field
        replaced with the value of the ``NonManifestDatasets.datasets`` field.
        """
        dataset = Dataset(dataset_id=unicode(uuid4()))
        datasets = {dataset.dataset_id: dataset}
        nonmanifest = NonManifestDatasets(datasets=datasets)
        deployment = DeploymentState()
        updated = nonmanifest.update_cluster_state(deployment)
        self.assertEqual(
            datasets, thaw(updated.nonmanifest_datasets)
        )


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


class GetNodeTests(SynchronousTestCase):
    """
    Tests for ``Deployment.get_node`` and ``DeploymentState.get_node``.
    """
    def test_deployment_with_node(self):
        """
        If the ``Deployment`` has a ``Node`` with a matching hostname,
        ``get_node`` returns it.
        """
        identifier = u"127.0.0.1"
        node = Node(hostname=identifier, applications={APP1})
        trap = Node(hostname=u"192.168.1.1")
        config = Deployment(nodes={node, trap})
        self.assertEqual(node, config.get_node(identifier))

    def test_deployment_without_node(self):
        """
        If the ``Deployment`` has no ``Node`` with a matching hostname,
        ``get_node`` returns a new empty ``Node`` with the given hostname.
        """
        identifier = u"127.0.0.1"
        trap = Node(hostname=u"192.168.1.1")
        config = Deployment(nodes={trap})
        self.assertEqual(
            Node(hostname=identifier), config.get_node(identifier)
        )

    def test_deploymentstate_with_node(self):
        """
        If the ``Deployment`` has a ``NodeState`` with a matching hostname,
        ``get_nodes`` returns it.
        """
        identifier = u"127.0.0.1"
        node = NodeState(hostname=identifier)
        state = DeploymentState(nodes={node})
        self.assertIs(node, state.get_node(identifier))

    def test_deploymentstate_without_node(self):
        """
        If the ``DeploymentState`` has no ``NodeState`` with a matching
        hostname, ``get_node`` returns a new empty ``NodeState`` with the given
        hostname.
        """
        identifier = u"127.0.0.1"
        trap = NodeState(hostname=u"192.168.1.1")
        state = DeploymentState(nodes={trap})
        self.assertEqual(
            NodeState(hostname=identifier), state.get_node(identifier)
        )


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

    def test_move_application(self):
        """
        Moving an ``Application`` from one node to another results in a new
        ``Deployment`` instance reflecting the updated configuration.
        """
        application = Application(
            name=u"mycontainer",
            image=DockerImage.from_string(u"busybox")
        )
        original_nodes = [
            Node(
                hostname=u"192.0.2.1",
                applications=[application]
            ),
            Node(
                hostname=u"192.0.2.2",
                applications=[]
            ),
        ]
        updated_nodes = [
            Node(
                hostname=u"192.0.2.1",
                applications=[]
            ),
            Node(
                hostname=u"192.0.2.2",
                applications=[application]
            ),
        ]
        original = Deployment(nodes=original_nodes)
        expected = Deployment(nodes=updated_nodes)
        updated = original.move_application(application, original_nodes[1])
        self.assertEqual(updated, expected)

    def test_move_non_existent_application(self):
        """
        Attempting to move an ``Application`` that does not exist on the
        cluster has no effect and therefore results in an identical
        ``Deployment`` instance to the one we started with.
        """
        application = Application(
            name=u"mycontainer",
            image=DockerImage.from_string(u"busybox")
        )
        existing_application = Application(
            name=u"realbusybox",
            image=DockerImage.from_string(u"busybox")
        )
        nodes = [
            Node(
                hostname=u"192.0.2.1",
                applications=[existing_application]
            ),
            Node(
                hostname=u"192.0.2.2",
                applications=[]
            ),
        ]
        original = Deployment(nodes=nodes)
        updated = original.move_application(application, nodes[1])
        self.assertEqual(original, updated)

    def test_move_application_new_node(self):
        """
        Moving an ``Application`` from one node to another not previously in
        this deployment results in a new ``Deployment`` instance reflecting
        the updated configuration.
        """
        application = Application(
            name=u"mycontainer",
            image=DockerImage.from_string(u"busybox")
        )
        original_nodes = [
            Node(
                hostname=u"192.0.2.1",
                applications=[application]
            ),
            Node(
                hostname=u"192.0.2.2",
                applications=[]
            ),
        ]
        updated_nodes = [
            Node(
                hostname=u"192.0.2.1",
                applications=[]
            ),
            Node(
                hostname=u"192.0.2.2",
                applications=[]
            ),
            Node(
                hostname=u"192.0.2.3",
                applications=[application]
            ),
        ]
        original = Deployment(nodes=original_nodes)
        expected = Deployment(nodes=updated_nodes)
        updated = original.move_application(
            application,
            Node(hostname=u"192.0.2.3")
        )
        self.assertEqual(updated, expected)

    def test_move_application_same_node(self):
        """
        Moving an ``Application`` from one node to where the target node is
        the same node as currently hosts the application results in a
        ``Deployment`` instance identical to the one we started with.
        """
        application = Application(
            name=u"mycontainer",
            image=DockerImage.from_string(u"busybox")
        )
        nodes = [
            Node(
                hostname=u"192.0.2.1",
                applications=[application]
            ),
            Node(
                hostname=u"192.0.2.2",
                applications=[]
            ),
        ]
        original = Deployment(nodes=nodes)
        updated = original.move_application(application, nodes[0])
        self.assertEqual(original, updated)


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

    def test_default_non_optional(self):
        """
        By default ``pset_field`` is non-optional, i.e. does not allow
        ``None``.
        """
        class Record(PRecord):
            value = pset_field(int)
        self.assertRaises(TypeError, Record, value=None)

    def test_explicit_non_optional(self):
        """
        If ``optional`` argument is ``False`` then ``pset_field`` is
        non-optional, i.e. does not allow ``None``.
        """
        class Record(PRecord):
            value = pset_field(int, optional=False)
        self.assertRaises(TypeError, Record, value=None)

    def test_optional(self):
        """
        If ``optional`` argument is true, ``None`` is acceptable alternative
        to a set.
        """
        class Record(PRecord):
            value = pset_field(int, optional=True)
        assert ((Record(value=[1, 2]).value, Record(value=None).value) ==
                (pset([1, 2]), None))

    def test_name(self):
        """
        The created set class name is based on the type of items in the set.
        """
        class Something(object):
            pass

        class Record(PRecord):
            value = pset_field(Something)
            value2 = pset_field(int)
        assert ((Record().value.__class__.__name__,
                 Record().value2.__class__.__name__) ==
                ("SomethingPSet", "IntPSet"))


class PMapFieldTests(SynchronousTestCase):
    """
    Tests for ``pmap_field``.

    This will hopefully be contributed upstream to pyrsistent, thus the
    slightly different testing style.
    """
    def test_initial_value(self):
        """
        ``pmap_field`` results in initial value that is empty.
        """
        class Record(PRecord):
            value = pmap_field(int, int)
        assert Record() == Record(value={})

    def test_factory(self):
        """
        ``pmap_field`` has a factory that creates a ``PMap``.
        """
        class Record(PRecord):
            value = pmap_field(int, int)
        record = Record(value={1:  1234})
        assert isinstance(record.value, PMap)

    def test_checked_map_key(self):
        """
        ``pmap_field`` results in a map that enforces its key type.
        """
        class Record(PRecord):
            value = pmap_field(int, type(None))
        record = Record(value={1: None})
        self.assertRaises(TypeError, record.value.set, "hello", None)

    def test_checked_map_value(self):
        """
        ``pmap_field`` results in a map that enforces its value type.
        """
        class Record(PRecord):
            value = pmap_field(int, type(None))
        record = Record(value={1: None})
        self.assertRaises(TypeError, record.value.set, 2, 4)

    def test_mandatory(self):
        """
        ``pmap_field`` is a mandatory field.
        """
        class Record(PRecord):
            value = pmap_field(int, int)
        record = Record()
        self.assertRaises(InvariantException, record.remove, "value")

    def test_default_non_optional(self):
        """
        By default ``pmap_field`` is non-optional, i.e. does not allow
        ``None``.
        """
        class Record(PRecord):
            value = pmap_field(int, int)
        # Ought to be TypeError, but pyrsistent doesn't quite allow that:
        self.assertRaises(AttributeError, Record, value=None)

    def test_explicit_non_optional(self):
        """
        If ``optional`` argument is ``False`` then ``pmap_field`` is
        non-optional, i.e. does not allow ``None``.
        """
        class Record(PRecord):
            value = pmap_field(int, int, optional=False)
        # Ought to be TypeError, but pyrsistent doesn't quite allow that:
        self.assertRaises(AttributeError, Record, value=None)

    def test_optional(self):
        """
        If ``optional`` argument is true, ``None`` is acceptable alternative
        to a set.
        """
        class Record(PRecord):
            value = pmap_field(int, int, optional=True)
        self.assertEqual(
            (Record(value={1: 2}).value, Record(value=None).value),
            (pmap({1: 2}), None))

    def test_name(self):
        """
        The created map class name is based on the types of items in the map.
        """
        class Something(object):
            pass

        class Another(object):
            pass

        class Record(PRecord):
            value = pmap_field(Something, Another)
            value2 = pmap_field(int, float)
        assert ((Record().value.__class__.__name__,
                 Record().value2.__class__.__name__) ==
                ("SomethingAnotherPMap", "IntFloatPMap"))

    def test_invariant(self):
        """
        The ``invariant`` parameter is passed through to ``field``.
        """
        class Record(PRecord):
            value = pmap_field(
                int, int,
                invariant=(
                    lambda pmap: (len(pmap) == 1, "Exactly one item required.")
                )
            )
        self.assertRaises(InvariantException, Record, value={})
        self.assertRaises(InvariantException, Record, value={1: 2, 3: 4})
        assert Record(value={1: 2}).value == {1: 2}


class DeploymentStateTests(SynchronousTestCase):
    """
    Tests for ``DeploymentState``.
    """
    def test_update_node_new(self):
        """
        When doing ``update_node()``, if the given ``NodeState`` has hostname
        not in the existing ``DeploymentState`` then just add new
        ``NodeState`` to new ``DeploymentState``.
        """
        dataset_id = unicode(uuid4())
        manifestation = Manifestation(dataset=Dataset(dataset_id=dataset_id),
                                      primary=True)
        node = NodeState(
            hostname=u"node1.example.com",
            applications={Application(
                name=u'postgresql-clusterhq',
                image=DockerImage.from_string(u"image"))},
            manifestations={dataset_id: manifestation})
        another_node = NodeState(
            hostname=u"node2.example.com",
            applications=frozenset({Application(
                name=u'site-clusterhq.com',
                image=DockerImage.from_string(u"image"))}),
        )
        original = DeploymentState(nodes=[node])
        updated = original.update_node(another_node)
        self.assertEqual((original, updated),
                         (DeploymentState(nodes=[node]),
                          DeploymentState(nodes=[node, another_node])))

    def test_update_node_replace(self):
        """
        When doing ``update_node()``, if the given ``NodeState`` has hostname
        in existing ``DeploymentState`` node then update all non-``None``
        attributes that ``NodeState`` in the new ``Deployment``.
        """
        dataset_id = unicode(uuid4())
        manifestation = Manifestation(dataset=Dataset(dataset_id=dataset_id),
                                      primary=True)
        end_node = NodeState(
            hostname=u"node1.example.com",
            applications=frozenset({Application(
                name=u'site-clusterhq.com',
                image=DockerImage.from_string(u"image"))}),
            used_ports=[1, 2],
            paths={dataset_id: FilePath(b"/xxx")},
            manifestations={dataset_id: manifestation})

        update_applications = end_node.update(dict(
            manifestations=None,
            paths=None,
        ))
        update_manifestations = end_node.update(dict(
            applications=None,
            used_ports=None,
        ))

        original = DeploymentState(
            nodes=[NodeState(hostname=u"node1.example.com")])
        updated = original.update_node(update_applications).update_node(
            update_manifestations)
        self.assertEqual(updated, DeploymentState(nodes=[end_node]))

    def test_nonmanifest_datasets_keys_are_their_ids(self):
        """
        The keys of the ``nonmanifest_datasets`` attribute must match the
        value's ``dataset_id`` attribute.
        """
        self.assertRaises(InvariantException,
                          DeploymentState,
                          nonmanifest_datasets={u"123": MANIFESTATION.dataset})
