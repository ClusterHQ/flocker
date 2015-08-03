# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._model``.
"""

from uuid import uuid4, UUID

from pyrsistent import (
    InvariantException, pset, PRecord, PSet, pmap, PMap, thaw, PVector,
    pvector
)

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from zope.interface.verify import verifyObject

from ...testtools import make_with_init_tests
from .._model import pset_field, pmap_field, pvector_field, ip_to_uuid

from .. import (
    IClusterStateChange, IClusterStateWipe,
    Application, DockerImage, Node, Deployment, AttachedVolume, Dataset,
    RestartOnFailure, RestartAlways, RestartNever, Manifestation,
    NodeState, DeploymentState, NonManifestDatasets, same_node,
    Link,
)


class IPToUUIDTests(SynchronousTestCase):
    """
    Tests for ``ip_to_uuid``.
    """
    def test_uuid(self):
        """
        ``ip_to_uuid`` returns a UUID.
        """
        uuid = ip_to_uuid(u"1.2.3.4")
        self.assertIsInstance(uuid, UUID)

    def test_stable(self):
        """
        ``ip_to_uuid`` returns the same UUID given the same IP.
        """
        self.assertEqual(ip_to_uuid(u"1.2.3.4"), ip_to_uuid(u"1.2.3.4"))

    def test_different(self):
        """
        ``ip_to_uuid`` returns different UUIDs for different IPs.
        """
        self.assertNotEqual(ip_to_uuid(u"1.2.3.5"), ip_to_uuid(u"1.2.3.6"))


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
        kwargs=dict(uuid=uuid4(), applications=pset([
            Application(name=u'mysql-clusterhq', image=DockerImage.from_string(
                u"image")),
            Application(name=u'site-clusterhq.com',
                        image=DockerImage.from_string(u"another")),
        ]))
)):
    """
    Tests for ``Node.__init__``.
    """
    def test_no_uuid(self):
        """
        If no UUID is given, a UUID is generated from the hostname.

        This is done for backwards compatibility with existing tests, and
        should be removed eventually.
        """
        node = Node(hostname=u'1.2.3.4')
        self.assertIsInstance(node.uuid, UUID)

    def test_uuid(self):
        """
        ``Node`` can be created with a UUID.
        """
        uuid = uuid4()
        node = Node(uuid=uuid)
        self.assertEqual(node.uuid, uuid)


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
    def test_no_uuid(self):
        """
        If no UUID is given, a UUID is generated from the hostname.

        This is done for backwards compatibility with existing tests, and
        should be removed eventually.
        """
        node = NodeState(hostname=u'1.2.3.4')
        self.assertIsInstance(node.uuid, UUID)

    def test_uuid(self):
        """
        ``NodeState`` can be created with a UUID.
        """
        uuid = uuid4()
        node = NodeState(hostname=u'1.2.3.4', uuid=uuid)
        self.assertEqual(node.uuid, uuid)

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
        app_state = node.set(applications=apps, used_ports=[])
        data_state = node.set(manifestations=manifestations,
                              devices={}, paths={})
        cluster = DeploymentState(nodes={app_state})
        changed_cluster = data_state.update_cluster_state(cluster)
        self.assertEqual(
            DeploymentState(nodes={
                NodeState(
                    hostname=hostname,
                    applications=apps,
                    manifestations=manifestations,
                    devices={}, paths={}, used_ports={},
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

    def test_completely_ignorant_by_default(self):
        """
        A newly created ``NodeState`` is completely ignorant.
        """
        node_state = NodeState(hostname=u"1.2.3.4", uuid=uuid4())
        self.assertEqual(
            [node_state.used_ports, node_state.applications,
             node_state.manifestations, node_state.paths, node_state.devices,
             node_state._provides_information()],
            [None, None, None, None, None, False])

    def assert_required_field_set(self, **fields):
        """
        Assert that if one of the given field names is set on a ``NodeState``,
        all of them must be set or this will be consideted an invariant
        violation.

        :param fields: ``NodeState`` attributes that are all expected to
            be settable as a group, but which cannot be missing if one of
            the others is set.
        """
        # If all are set, no problems:
        NodeState(hostname=u"127.0.0.1", uuid=uuid4(), **fields)
        # If one is missing, an invariant is raised:
        for name in fields:
            remaining_fields = fields.copy()
            del remaining_fields[name]
            self.assertRaises(InvariantException, NodeState,
                              hostname=u"127.0.0.1", uuid=uuid4(),
                              **remaining_fields)

    def test_application_fields(self):
        """
        Both ``applications`` and ``used_ports`` must be set if one of them is
        set.
        """
        self.assert_required_field_set(applications=[], used_ports={})

    def test_dataset_fields(self):
        """
        ``manifestations``, ``devices`` and ``paths`` must be set if one of
        them is set.
        """
        self.assert_required_field_set(manifestations={}, paths={}, devices={})


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
        ip = u"127.0.0.1"
        identifier = uuid4()
        node = Node(uuid=identifier, hostname=ip, applications={APP1})
        trap = Node(uuid=uuid4(), hostname=u"192.168.1.1")
        config = Deployment(nodes={node, trap})
        self.assertEqual(node, config.get_node(identifier))

    def test_deployment_without_node(self):
        """
        If the ``Deployment`` has no ``Node`` with a matching hostname,
        ``get_node`` returns a new empty ``Node`` with the given hostname.
        """
        ip = u"127.0.0.1"
        identifier = uuid4()
        trap = Node(uuid=uuid4(), hostname=u"192.168.1.1")
        config = Deployment(nodes={trap})
        self.assertEqual(
            Node(uuid=identifier, hostname=ip),
            config.get_node(identifier, hostname=ip)
        )

    def test_deploymentstate_with_node(self):
        """
        If the ``Deployment`` has a ``NodeState`` with a matching uuid,
        ``get_nodes`` returns it.
        """
        ip = u"127.0.0.1"
        identifier = uuid4()
        node = NodeState(uuid=identifier, hostname=ip)
        state = DeploymentState(nodes={node})
        self.assertIs(node, state.get_node(identifier))

    def test_deploymentstate_without_node(self):
        """
        If the ``DeploymentState`` has no ``NodeState`` with a matching
        uuid, ``get_node`` returns a new empty ``NodeState`` with the given
        uuid and defaults.
        """
        identifier = uuid4()
        trap = NodeState(uuid=uuid4(), hostname=u"192.168.1.1")
        state = DeploymentState(nodes={trap})
        self.assertEqual(
            NodeState(uuid=identifier, hostname=u"1.2.3.4"),
            state.get_node(identifier, hostname=u"1.2.3.4"),
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

    def test_custom_initial(self):
        """
        A custom initial value can be passed in.
        """
        class Record(PRecord):
            value = pset_field(int, initial=(1, 2))
        assert Record() == Record(value=[1, 2])

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


class PVectorFieldTests(SynchronousTestCase):
    """
    Tests for ``pvector_field``.

    This will hopefully be contributed upstream to pyrsistent, thus the
    slightly different testing style.
    """
    def test_initial_value(self):
        """
        ``pvector_field`` results in initial value that is empty.
        """
        class Record(PRecord):
            value = pvector_field(int)
        assert Record() == Record(value=[])

    def test_custom_initial(self):
        """
        A custom initial value can be passed in.
        """
        class Record(PRecord):
            value = pvector_field(int, initial=(1, 2))
        assert Record() == Record(value=[1, 2])

    def test_factory(self):
        """
        ``pvector_field`` has a factory that creates a ``PVector``.
        """
        class Record(PRecord):
            value = pvector_field(int)
        record = Record(value=[1, 2])
        assert isinstance(record.value, PVector)

    def test_checked_vector(self):
        """
        ``pvector_field`` results in a vector that enforces its type.
        """
        class Record(PRecord):
            value = pvector_field(int)
        record = Record(value=[1, 2])
        self.assertRaises(TypeError, record.value.append, "hello")

    def test_type(self):
        """
        ``pvector_field`` enforces its type.
        """
        class Record(PRecord):
            value = pvector_field(int)
        record = Record()
        self.assertRaises(TypeError, record.set, "value", None)

    def test_mandatory(self):
        """
        ``pvector_field`` is a mandatory field.
        """
        class Record(PRecord):
            value = pvector_field(int)
        record = Record(value=[1])
        self.assertRaises(InvariantException, record.remove, "value")

    def test_default_non_optional(self):
        """
        By default ``pvector_field`` is non-optional, i.e. does not allow
        ``None``.
        """
        class Record(PRecord):
            value = pvector_field(int)
        self.assertRaises(TypeError, Record, value=None)

    def test_explicit_non_optional(self):
        """
        If ``optional`` argument is ``False`` then ``pvector_field`` is
        non-optional, i.e. does not allow ``None``.
        """
        class Record(PRecord):
            value = pvector_field(int, optional=False)
        self.assertRaises(TypeError, Record, value=None)

    def test_optional(self):
        """
        If ``optional`` argument is true, ``None`` is acceptable alternative
        to a sequence.
        """
        class Record(PRecord):
            value = pvector_field(int, optional=True)
        assert ((Record(value=[1, 2]).value, Record(value=None).value) ==
                (pvector([1, 2]), None))

    def test_name(self):
        """
        The created set class name is based on the type of items in the set.
        """
        class Something(object):
            pass

        class Record(PRecord):
            value = pvector_field(Something)
            value2 = pvector_field(int)
        assert ((Record().value.__class__.__name__,
                 Record().value2.__class__.__name__) ==
                ("SomethingPVector", "IntPVector"))


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

    def test_override_initial_value(self):
        """
        The initial value can be set to a non-empty map by passing the desired
        value to the ``initial`` parameter.
        """
        initial = {1: 2, 3: 4}

        class Record(PRecord):
            value = pmap_field(int, int, initial=initial)
        assert Record() == Record(value=initial)

    def test_none_initial_value(self):
        """
        The initial value for an optional field can be set to ``None`` by
        passing ``None`` to the ``initial`` parameter.
        """
        initial = None

        class Record(PRecord):
            value = pmap_field(int, int, optional=True, initial=initial)
        assert Record() == Record(value=initial)

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
            used_ports=[],
            manifestations={dataset_id: manifestation},
            devices={}, paths={})
        another_node = NodeState(
            hostname=u"node2.example.com",
            applications=frozenset({Application(
                name=u'site-clusterhq.com',
                image=DockerImage.from_string(u"image"))}),
            used_ports=[],
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
            devices={},
            manifestations={dataset_id: manifestation})

        update_applications = end_node.update(dict(
            manifestations=None,
            paths=None, devices=None,
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

    def test_all_datasets(self):
        """
        ``all_datasets`` returns an iterator of
        2-tuple(``Dataset``, ``Node`` or ``None``)
        for all primary manifest datasets and all non-manifest datasets in the
        ``DeploymentState``.
        """
        nonmanifest_id = unicode(uuid4())

        expected_nodestate = NodeState(
            uuid=uuid4(), hostname=u"192.0.2.5",
            applications={}, used_ports={},
            manifestations={
                MANIFESTATION.dataset_id: MANIFESTATION,
            },
            paths={
                MANIFESTATION.dataset_id: FilePath(b"/foo/bar"),
            },
            devices={
                UUID(MANIFESTATION.dataset_id): FilePath(b"/dev/foo"),
            },
        )

        deployment = DeploymentState(
            nodes={
                # A node for which we are ignorant of manifestations, should
                # contribute nothing to the result.
                NodeState(
                    uuid=uuid4(), hostname=u"192.0.2.4",
                    applications={}, used_ports={},
                    manifestations=None, paths=None, devices=None,
                ),
                # A node with a manifestation.
                expected_nodestate,
            },
            nonmanifest_datasets={
                # And one dataset with no manifestation anywhere.
                nonmanifest_id: Dataset(dataset_id=nonmanifest_id),
            },
        )
        self.assertEqual(
            [
                (MANIFESTATION.dataset, expected_nodestate),
                (Dataset(dataset_id=nonmanifest_id), None),
            ],
            list(deployment.all_datasets()),
        )

    def test_all_datasets_excludes_replicas(self):
        """
        ``all_datasets`` does not return replica manifestations.
        """
        replica = Manifestation(
            dataset=Dataset(dataset_id=unicode(uuid4())),
            primary=False
        )
        deployment = DeploymentState(
            nodes={
                # A node with a replica manifestation only.
                NodeState(
                    uuid=uuid4(), hostname=u"192.0.2.5",
                    applications={}, used_ports={},
                    manifestations={
                        replica.dataset_id: replica,
                    },
                    paths={
                        replica.dataset.dataset_id: FilePath(b"/foo/replica"),
                    },
                    devices={
                        UUID(replica.dataset.dataset_id):
                        FilePath(b"/dev/replica"),
                    },
                )
            },
        )
        self.assertEqual([], list(deployment.all_datasets()))


class SameNodeTests(SynchronousTestCase):
    """
    Tests for ``same_node``.
    """
    def test_node(self):
        """
        ``same_node`` returns ``True`` if two ``Node``s have the same UUID.
        """
        node1 = Node(uuid=uuid4(), hostname=u"1.2.3.4")
        node2 = Node(uuid=node1.uuid, hostname=u"1.2.3.5")
        node3 = Node(uuid=uuid4(), hostname=u"1.2.3.4")
        self.assertEqual([same_node(node1, node2), same_node(node1, node3)],
                         [True, False])

    def test_nodestate(self):
        """
        ``same_node`` returns ``True`` if two ``NodeState``s have the same
        UUID.
        """
        node1 = NodeState(uuid=uuid4(), hostname=u"1.2.3.4")
        node2 = NodeState(uuid=node1.uuid, hostname=u"1.2.3.5")
        node3 = NodeState(uuid=uuid4(), hostname=u"1.2.3.4")
        self.assertEqual([same_node(node1, node2), same_node(node1, node3)],
                         [True, False])

    def test_both(self):
        """
        ``same_node`` returns ``True`` if a ``Node`` and ``NodeState`` have
        the same UUID.
        """
        node1 = Node(uuid=uuid4(), hostname=u"1.2.3.4")
        node2 = NodeState(uuid=node1.uuid, hostname=u"1.2.3.5")
        node3 = NodeState(uuid=uuid4(), hostname=u"1.2.3.4")
        self.assertEqual([same_node(node1, node2), same_node(node1, node3)],
                         [True, False])


class NodeStateWipingTests(SynchronousTestCase):
    """
    Tests for ``NodeState.get_information_wipe``.
    """
    NODE_FROM_APP_AGENT = NodeState(hostname=u"1.2.3.4", uuid=uuid4(),
                                    applications={APP1},
                                    used_ports={1, 2, 3},
                                    manifestations=None,
                                    paths=None,
                                    devices=None)
    APP_WIPE = NODE_FROM_APP_AGENT.get_information_wipe()

    NODE_FROM_DATASET_AGENT = NodeState(hostname=NODE_FROM_APP_AGENT.hostname,
                                        uuid=NODE_FROM_APP_AGENT.uuid,
                                        applications=None, used_ports=None,
                                        manifestations={
                                            MANIFESTATION.dataset_id:
                                            MANIFESTATION},
                                        devices={}, paths={})
    DATASET_WIPE = NODE_FROM_DATASET_AGENT.get_information_wipe()

    def test_interface(self):
        """
        The object returned from ``NodeStateWipe`` implements
        ``IClusterStateWipe``.
        """
        self.assertTrue(verifyObject(IClusterStateWipe, self.APP_WIPE))

    def test_key_differs_by_uuid(self):
        """
        The ``IClusterStateWipe`` has different keys for different node UUIDs.
        """
        node2 = self.NODE_FROM_APP_AGENT.set("uuid", uuid4())
        self.assertNotEqual(node2.get_information_wipe().key(),
                            self.APP_WIPE.key())

    def test_key_differs_by_attributes(self):
        """
        The ``IClusterStateWipe`` has different keys for different attributes
        being wiped.
        """
        self.assertNotEqual(self.APP_WIPE.key(), self.DATASET_WIPE.key())

    def test_key_same_by_attribute_contents(self):
        """
        The ``IClusterStateWipe`` has the same key if it is wiping same
        attributes on same node.
        """
        different_apps_node = self.NODE_FROM_APP_AGENT.set(
            "applications", {APP2}, "used_ports", {4, 5})

        self.assertEqual(self.APP_WIPE.key(),
                         different_apps_node.get_information_wipe().key())

    def test_applying_node_does_not_exist(self):
        """
        Applying the ``IClusterStateWipe`` when the node indicated does not
        exist returns the same ``DeploymentState``.
        """
        cluster = DeploymentState()
        self.assertEqual(cluster, self.APP_WIPE.update_cluster_state(cluster))

    def test_applying_indicates_ignorance(self):
        """
        Applying the ``IClusterStateWipe`` removes attributes matching the
        original ``NodeState`` information.
        """
        # Cluster has combination of application and dataset information:
        cluster = DeploymentState(nodes={self.NODE_FROM_APP_AGENT})
        cluster = self.NODE_FROM_DATASET_AGENT.update_cluster_state(cluster)
        # We wipe application information:
        cluster = self.APP_WIPE.update_cluster_state(cluster)
        # Result should be same as just having dataset information:
        self.assertEqual(
            cluster,
            DeploymentState(nodes=[self.NODE_FROM_DATASET_AGENT]))

    def test_applying_removes_node(self):
        """
        Applying the ``IClusterStateWipe`` removes the ``NodeState`` outright
        if nothing more is known about it.
        """
        node_2 = NodeState(hostname=u"1.2.3.5", uuid=uuid4())
        # Cluster has only dataset information for a node:
        cluster = DeploymentState(nodes=[
            self.NODE_FROM_APP_AGENT, node_2])
        # We wipe the dataset information:
        cluster = self.APP_WIPE.update_cluster_state(cluster)
        # Result should remove node about which we know nothing:
        self.assertEqual(
            cluster,
            DeploymentState(nodes={node_2}))


class NonManifestDatasetsWipingTests(SynchronousTestCase):
    """
    Tests for ``NonManifestDatasets.get_information_wipe()``.
    """
    NON_MANIFEST = NonManifestDatasets(datasets={MANIFESTATION.dataset_id:
                                                 MANIFESTATION.dataset})
    WIPE = NON_MANIFEST.get_information_wipe()

    def test_interface(self):
        """
        The object returned from ``NodeStateWipe`` implements
        ``IClusterStateWipe``.
        """
        self.assertTrue(verifyObject(IClusterStateWipe, self.WIPE))

    def test_key_always_the_same(self):
        """
        The ``IClusterStateWipe`` always has the same key.
        """
        self.assertEqual(
            NonManifestDatasets().get_information_wipe().key(),
            self.WIPE.key())

    def test_applying_does_nothing(self):
        """
        Applying the ``IClusterStateWipe`` does nothing to the cluster state.
        """
        # Cluster has some non-manifested datasets:
        cluster_state = self.NON_MANIFEST.update_cluster_state(
            DeploymentState())

        # "Wiping" this information has no effect:
        updated = self.WIPE.update_cluster_state(cluster_state)
        self.assertEqual(updated, cluster_state)


class LinkTests(SynchronousTestCase):
    """
    Tests for ``Link``.
    """
    def test_case_insensitive(self):
        """
        Link aliases are case insensitive as far as comparison goes.
        """
        link = Link(alias=u'myLINK', local_port=1, remote_port=1)
        link2 = link.set('alias', u'MYlink')
        self.assertEqual(link, link2)
