# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._model``.
"""

import datetime

from uuid import uuid4, UUID

from pyrsistent import (
    InvariantException, pset, PClass, PSet, pmap, PMap, thaw, PVector,
    pvector, PRecord
)

from twisted.python.filepath import FilePath

from hypothesis import given, assume
from hypothesis.strategies import sampled_from

from zope.interface.verify import verifyObject

from testtools.matchers import Equals

from ...testtools import make_with_init_tests, TestCase
from .._model import pset_field, pmap_field, pvector_field, ip_to_uuid

from .. import (
    IClusterStateChange, IClusterStateWipe,
    Application, DockerImage, Node, Deployment, AttachedVolume, Dataset,
    RestartOnFailure, RestartAlways, RestartNever, Manifestation,
    NodeState, DeploymentState, NonManifestDatasets, same_node,
    Link, Lease, Leases, LeaseError, UpdateNodeStateEra, NoWipe,
)


class IPToUUIDTests(TestCase):
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


class DockerImageTests(TestCase):
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


class DockerImageFromStringTests(TestCase):
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
        kwargs=dict(uuid=uuid4(), applications={a.name: a for a in [
            Application(name=u'mysql-clusterhq', image=DockerImage.from_string(
                u"image")),
            Application(name=u'site-clusterhq.com',
                        image=DockerImage.from_string(u"another")),
        ]})
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


class ManifestationTests(TestCase):
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


class NodeTests(TestCase):
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
            applications={a.name: a for a in [
                APP1,
                Application(name=u'a',
                            image=DockerImage.from_string(u'x'),
                            volume=AttachedVolume(
                                manifestation=m1,
                                mountpoint=FilePath(b"/xxx"))),
            ]})

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
                    applications={
                        u'a': Application(
                            name=u'a',
                            image=DockerImage.from_string(u'x'),
                            volume=AttachedVolume(
                                manifestation=m1,
                                mountpoint=FilePath(b"/xxx")))
                    },
                    manifestations={m1.dataset_id: m1,
                                    m2.dataset_id: m2})

        self.assertEqual(node.manifestations, {m1.dataset_id: m1,
                                               m2.dataset_id: m2})

    def test_applications_contains_applications(self):
        """
        ``Node.applications`` must be ``Application`` instances.
        """
        self.assertRaises(TypeError,
                          Node, hostname=u"xxx", applications={u'': None})
        self.assertRaises(TypeError,
                          Node, hostname=u"xxx", applications={'': APP1})

    def test_application_keys_are_their_names(self):
        """
        ``Node.applications`` keys are the name of the application
        """
        self.assertRaises(InvariantException,
                          Node, hostname=u"xxx", applications={
                              APP1.name + '.post': APP1})

    def test_manifestations_keys_are_their_ids(self):
        """
        The keys of the ``manifestations`` attribute must match the
        value's ``dataset_id`` attribute.
        """
        self.assertRaises(InvariantException,
                          Node, hostname=u"xxx",
                          manifestations={u"123": MANIFESTATION})


class NodeStateTests(TestCase):
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
        apps = {APP1.name: APP1}
        manifestations = {MANIFESTATION.dataset_id: MANIFESTATION}
        node = NodeState(
            hostname=hostname,
            applications=None,
            manifestations=None,
        )
        app_state = node.set(applications=apps)
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
                    devices={}, paths={},
                )
            }),
            changed_cluster
        )

    def test_application_keys_are_their_names(self):
        """
        The keys of the ``applications`` attribute must match the value's
        ``name`` attribute.
        """
        self.assertRaises(InvariantException,
                          NodeState, hostname=u"xxx",
                          applications={APP1.name + '.post': APP1})

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

    def test_completely_ignorant_by_default(self):
        """
        A newly created ``NodeState`` is completely ignorant.
        """
        node_state = NodeState(hostname=u"1.2.3.4", uuid=uuid4())
        self.assertEqual(
            [node_state.applications,
             node_state.manifestations, node_state.paths, node_state.devices,
             node_state._provides_information()],
            [None, None, None, None, False])

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


class NonManifestDatasetsTests(TestCase):
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
        kwargs=dict(nodes={n.uuid: n for n in [
            Node(hostname=u'node1.example.com', applications={}),
            Node(hostname=u'node2.example.com', applications={})
        ]})
)):
    """
    Tests for ``Deployment.__init__``.
    """


class GetNodeTests(TestCase):
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
        node = Node(uuid=identifier, hostname=ip,
                    applications={APP1.name: APP1})
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


class DeploymentTests(TestCase):
    """
    Tests for ``Deployment``.
    """
    def test_applications(self):
        """
        ``Deployment.applications()`` returns applications from all nodes.
        """
        node = Node(
            hostname=u"node1.example.com",
            applications={a.name: a for a in [
                Application(name=u'mysql-clusterhq',
                            image=DockerImage.from_string(u"image")),
                Application(name=u'site-clusterhq.com',
                            image=DockerImage.from_string(u"image"))
            ]},
        )
        another_node = Node(
            hostname=u"node2.example.com",
            applications={u'site-clusterhq.com': Application(
                name=u'site-clusterhq.com',
                image=DockerImage.from_string(u"image"))},
        )
        deployment = Deployment(nodes=frozenset([node, another_node]))
        self.assertEqual(
            set(deployment.applications()),
            set(node.applications.values()) |
            set(another_node.applications.values()))

    def test_update_node_retains_leases(self):
        """
        ``update_node()`` retains the existing ``Deployment``'s leases
        and does not transform them.
        """
        node = Node(
            hostname=u"node1.example.com",
            applications={
                u'postgresql-clusterhq': Application(
                    name=u'postgresql-clusterhq',
                    image=DockerImage.from_string(u"image"))
            }
        )
        another_node = Node(
            hostname=u"node2.example.com",
            applications={
                u'site-clusterhq.com': Application(
                    name=u'site-clusterhq.com',
                    image=DockerImage.from_string(u"image"))
            },
        )
        dataset_id = uuid4()
        leases = Leases()
        leases = leases.acquire(
            datetime.datetime.now(), dataset_id, node.uuid, 60
        )
        original = Deployment(nodes=frozenset([node]), leases=leases)
        updated = original.update_node(another_node)
        self.assertEqual(original.leases, updated.leases)

    def test_update_node_new(self):
        """
        When doing ``update_node()``, if the given ``Node`` has hostname not
        in existing ``Deployment`` then just add new ``Node`` to new
        ``Deployment``.
        """
        node = Node(
            hostname=u"node1.example.com",
            applications={
                u'postgresql-clusterhq': Application(
                    name=u'postgresql-clusterhq',
                    image=DockerImage.from_string(u"image"))})
        another_node = Node(
            hostname=u"node2.example.com",
            applications={
                u'site-clusterhq.com': Application(
                    name=u'site-clusterhq.com',
                    image=DockerImage.from_string(u"image"))},
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
            applications={
                u'postgresql-clusterhq': Application(
                    name=u'postgresql-clusterhq',
                    image=DockerImage.from_string(u"image"))})
        another_node = Node(
            hostname=u"node2.example.com",
            applications={
                u'site-clusterhq.com': Application(
                    name=u'site-clusterhq.com',
                    image=DockerImage.from_string(u"image"))},
        )
        updated_node = Node(
            hostname=u"node1.example.com",
            applications={})

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
                applications={application.name: application}
            ),
            Node(
                hostname=u"192.0.2.2",
                applications={}
            ),
        ]
        updated_nodes = [
            Node(
                hostname=u"192.0.2.1",
                applications={}
            ),
            Node(
                hostname=u"192.0.2.2",
                applications={application.name: application}
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
                applications={existing_application.name: existing_application}
            ),
            Node(
                hostname=u"192.0.2.2",
                applications={}
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
                applications={application.name: application}
            ),
            Node(
                hostname=u"192.0.2.2",
                applications={}
            ),
        ]
        updated_nodes = [
            Node(
                hostname=u"192.0.2.1",
                applications={}
            ),
            Node(
                hostname=u"192.0.2.2",
                applications={}
            ),
            Node(
                hostname=u"192.0.2.3",
                applications={application.name: application}
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
                applications={application.name: application}
            ),
            Node(
                hostname=u"192.0.2.2",
                applications={}
            ),
        ]
        original = Deployment(nodes=nodes)
        updated = original.move_application(application, nodes[0])
        self.assertEqual(original, updated)


class RestartOnFailureTests(TestCase):
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


class AttachedVolumeTests(TestCase):
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


PYRSISTENT_STRUCT = sampled_from({PClass, PRecord})


class PSetFieldTests(TestCase):
    """
    Tests for ``pset_field``.

    This will hopefully be contributed upstream to pyrsistent, thus the
    slightly different testing style.
    """
    @given(PYRSISTENT_STRUCT)
    def test_initial_value(self, klass):
        """
        ``pset_field`` results in initial value that is empty.
        """
        class Record(klass):
            value = pset_field(int)
        assert Record() == Record(value=[])

    @given(PYRSISTENT_STRUCT)
    def test_custom_initial(self, klass):
        """
        A custom initial value can be passed in.
        """
        class Record(klass):
            value = pset_field(int, initial=(1, 2))
        assert Record() == Record(value=[1, 2])

    @given(PYRSISTENT_STRUCT)
    def test_factory(self, klass):
        """
        ``pset_field`` has a factory that creates a ``PSet``.
        """
        class Record(klass):
            value = pset_field(int)
        record = Record(value=[1, 2])
        assert isinstance(record.value, PSet)

    @given(PYRSISTENT_STRUCT)
    def test_checked_set(self, klass):
        """
        ``pset_field`` results in a set that enforces its type.
        """
        class Record(klass):
            value = pset_field(int)
        record = Record(value=[1, 2])
        self.assertRaises(TypeError, record.value.add, "hello")

    @given(PYRSISTENT_STRUCT)
    def test_type(self, klass):
        """
        ``pset_field`` enforces its type.
        """
        class Record(klass):
            value = pset_field(int)
        record = Record()
        self.assertRaises(TypeError, record.set, "value", None)

    @given(PYRSISTENT_STRUCT)
    def test_mandatory(self, klass):
        """
        ``pset_field`` is a mandatory field.
        """
        # PClass sets attributes to the initial value when you try to remove
        # them.
        assume(klass is PRecord)

        class Record(klass):
            value = pset_field(int)
        record = Record(value=[1])
        self.assertRaises(InvariantException, record.remove, "value")

    @given(PYRSISTENT_STRUCT)
    def test_default_non_optional(self, klass):
        """
        By default ``pset_field`` is non-optional, i.e. does not allow
        ``None``.
        """
        class Record(klass):
            value = pset_field(int)
        self.assertRaises(TypeError, Record, value=None)

    @given(PYRSISTENT_STRUCT)
    def test_explicit_non_optional(self, klass):
        """
        If ``optional`` argument is ``False`` then ``pset_field`` is
        non-optional, i.e. does not allow ``None``.
        """
        class Record(klass):
            value = pset_field(int, optional=False)
        self.assertRaises(TypeError, Record, value=None)

    @given(PYRSISTENT_STRUCT)
    def test_optional(self, klass):
        """
        If ``optional`` argument is true, ``None`` is acceptable alternative
        to a set.
        """
        class Record(klass):
            value = pset_field(int, optional=True)
        assert ((Record(value=[1, 2]).value, Record(value=None).value) ==
                (pset([1, 2]), None))

    @given(PYRSISTENT_STRUCT)
    def test_name(self, klass):
        """
        The created set class name is based on the type of items in the set.
        """
        class Something(object):
            pass

        class Record(klass):
            value = pset_field(Something)
            value2 = pset_field(int)
        assert ((Record().value.__class__.__name__,
                 Record().value2.__class__.__name__) ==
                ("SomethingPSet", "IntPSet"))


class PVectorFieldTests(TestCase):
    """
    Tests for ``pvector_field``.

    This will hopefully be contributed upstream to pyrsistent, thus the
    slightly different testing style.
    """
    @given(PYRSISTENT_STRUCT)
    def test_initial_value(self, klass):
        """
        ``pvector_field`` results in initial value that is empty.
        """
        class Record(klass):
            value = pvector_field(int)
        assert Record() == Record(value=[])

    @given(PYRSISTENT_STRUCT)
    def test_custom_initial(self, klass):
        """
        A custom initial value can be passed in.
        """
        class Record(klass):
            value = pvector_field(int, initial=(1, 2))
        assert Record() == Record(value=[1, 2])

    @given(PYRSISTENT_STRUCT)
    def test_factory(self, klass):
        """
        ``pvector_field`` has a factory that creates a ``PVector``.
        """
        class Record(klass):
            value = pvector_field(int)
        record = Record(value=[1, 2])
        assert isinstance(record.value, PVector)

    @given(PYRSISTENT_STRUCT)
    def test_checked_vector(self, klass):
        """
        ``pvector_field`` results in a vector that enforces its type.
        """
        class Record(klass):
            value = pvector_field(int)
        record = Record(value=[1, 2])
        self.assertRaises(TypeError, record.value.append, "hello")

    @given(PYRSISTENT_STRUCT)
    def test_type(self, klass):
        """
        ``pvector_field`` enforces its type.
        """
        class Record(klass):
            value = pvector_field(int)
        record = Record()
        self.assertRaises(TypeError, record.set, "value", None)

    @given(PYRSISTENT_STRUCT)
    def test_mandatory(self, klass):
        """
        ``pvector_field`` is a mandatory field.
        """
        # PClass sets attributes to the initial value when you try to remove
        # them.
        assume(klass is PRecord)

        class Record(klass):
            value = pvector_field(int)
        record = Record(value=[1])
        self.assertRaises(InvariantException, record.remove, "value")

    @given(PYRSISTENT_STRUCT)
    def test_default_non_optional(self, klass):
        """
        By default ``pvector_field`` is non-optional, i.e. does not allow
        ``None``.
        """
        class Record(klass):
            value = pvector_field(int)
        self.assertRaises(TypeError, Record, value=None)

    @given(PYRSISTENT_STRUCT)
    def test_explicit_non_optional(self, klass):
        """
        If ``optional`` argument is ``False`` then ``pvector_field`` is
        non-optional, i.e. does not allow ``None``.
        """
        class Record(klass):
            value = pvector_field(int, optional=False)
        self.assertRaises(TypeError, Record, value=None)

    @given(PYRSISTENT_STRUCT)
    def test_optional(self, klass):
        """
        If ``optional`` argument is true, ``None`` is acceptable alternative
        to a sequence.
        """
        class Record(klass):
            value = pvector_field(int, optional=True)
        assert ((Record(value=[1, 2]).value, Record(value=None).value) ==
                (pvector([1, 2]), None))

    @given(PYRSISTENT_STRUCT)
    def test_name(self, klass):
        """
        The created set class name is based on the type of items in the set.
        """
        class Something(object):
            pass

        class Record(klass):
            value = pvector_field(Something)
            value2 = pvector_field(int)
        assert ((Record().value.__class__.__name__,
                 Record().value2.__class__.__name__) ==
                ("SomethingPVector", "IntPVector"))


class PMapFieldTests(TestCase):
    """
    Tests for ``pmap_field``.

    This will hopefully be contributed upstream to pyrsistent, thus the
    slightly different testing style.
    """
    @given(PYRSISTENT_STRUCT)
    def test_initial_value(self, klass):
        """
        ``pmap_field`` results in initial value that is empty.
        """
        class Record(klass):
            value = pmap_field(int, int)
        assert Record() == Record(value={})

    @given(PYRSISTENT_STRUCT)
    def test_override_initial_value(self, klass):
        """
        The initial value can be set to a non-empty map by passing the desired
        value to the ``initial`` parameter.
        """
        initial = {1: 2, 3: 4}

        class Record(klass):
            value = pmap_field(int, int, initial=initial)
        assert Record() == Record(value=initial)

    @given(PYRSISTENT_STRUCT)
    def test_none_initial_value(self, klass):
        """
        The initial value for an optional field can be set to ``None`` by
        passing ``None`` to the ``initial`` parameter.
        """
        initial = None

        class Record(klass):
            value = pmap_field(int, int, optional=True, initial=initial)
        assert Record() == Record(value=initial)

    @given(PYRSISTENT_STRUCT)
    def test_factory(self, klass):
        """
        ``pmap_field`` has a factory that creates a ``PMap``.
        """
        class Record(klass):
            value = pmap_field(int, int)
        record = Record(value={1:  1234})
        assert isinstance(record.value, PMap)

    @given(PYRSISTENT_STRUCT)
    def test_checked_map_key(self, klass):
        """
        ``pmap_field`` results in a map that enforces its key type.
        """
        class Record(klass):
            value = pmap_field(int, type(None))
        record = Record(value={1: None})
        self.assertRaises(TypeError, record.value.set, "hello", None)

    @given(PYRSISTENT_STRUCT)
    def test_checked_map_value(self, klass):
        """
        ``pmap_field`` results in a map that enforces its value type.
        """
        class Record(klass):
            value = pmap_field(int, type(None))
        record = Record(value={1: None})
        self.assertRaises(TypeError, record.value.set, 2, 4)

    @given(PYRSISTENT_STRUCT)
    def test_mandatory(self, klass):
        """
        ``pmap_field`` is a mandatory field.
        """
        # PClass sets attributes to the initial value when you try to remove
        # them.
        assume(klass is PRecord)

        class Record(klass):
            value = pmap_field(int, int)
        record = Record()
        self.assertRaises(InvariantException, record.remove, "value")

    @given(PYRSISTENT_STRUCT)
    def test_default_non_optional(self, klass):
        """
        By default ``pmap_field`` is non-optional, i.e. does not allow
        ``None``.
        """
        class Record(klass):
            value = pmap_field(int, int)
        # Ought to be TypeError, but pyrsistent doesn't quite allow that:
        self.assertRaises(AttributeError, Record, value=None)

    @given(PYRSISTENT_STRUCT)
    def test_explicit_non_optional(self, klass):
        """
        If ``optional`` argument is ``False`` then ``pmap_field`` is
        non-optional, i.e. does not allow ``None``.
        """
        class Record(klass):
            value = pmap_field(int, int, optional=False)
        # Ought to be TypeError, but pyrsistent doesn't quite allow that:
        self.assertRaises(AttributeError, Record, value=None)

    @given(PYRSISTENT_STRUCT)
    def test_optional(self, klass):
        """
        If ``optional`` argument is true, ``None`` is acceptable alternative
        to a set.
        """
        class Record(klass):
            value = pmap_field(int, int, optional=True)
        self.assertEqual(
            (Record(value={1: 2}).value, Record(value=None).value),
            (pmap({1: 2}), None))

    @given(PYRSISTENT_STRUCT)
    def test_name(self, klass):
        """
        The created map class name is based on the types of items in the map.
        """
        class Something(object):
            pass

        class Another(object):
            pass

        class Record(klass):
            value = pmap_field(Something, Another)
            value2 = pmap_field(int, float)
        assert ((Record().value.__class__.__name__,
                 Record().value2.__class__.__name__) ==
                ("SomethingAnotherPMap", "IntFloatPMap"))

    @given(PYRSISTENT_STRUCT)
    def test_invariant(self, klass):
        """
        The ``invariant`` parameter is passed through to ``field``.
        """
        class Record(klass):
            value = pmap_field(
                int, int,
                invariant=(
                    lambda pmap: (len(pmap) == 1, "Exactly one item required.")
                )
            )
        self.assertRaises(InvariantException, Record, value={})
        self.assertRaises(InvariantException, Record, value={1: 2, 3: 4})
        assert Record(value={1: 2}).value == {1: 2}


class DeploymentStateTests(TestCase):
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
            applications={
                u'postgresql-clusterhq': Application(
                    name=u'postgresql-clusterhq',
                    image=DockerImage.from_string(u"image"))},
            manifestations={dataset_id: manifestation},
            devices={}, paths={})
        another_node = NodeState(
            hostname=u"node2.example.com",
            applications={
                u'site-clusterhq.com': Application(
                    name=u'site-clusterhq.com',
                    image=DockerImage.from_string(u"image"))},
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
            applications={
                u'site-clusterhq.com': Application(
                    name=u'site-clusterhq.com',
                    image=DockerImage.from_string(u"image"))},
            paths={dataset_id: FilePath(b"/xxx")},
            devices={},
            manifestations={dataset_id: manifestation})

        update_applications = end_node.update(dict(
            manifestations=None,
            paths=None, devices=None,
        ))
        update_manifestations = end_node.update(dict(
            applications=None,
        ))

        original = DeploymentState(
            nodes=[NodeState(hostname=u"node1.example.com")])
        updated = original.update_node(update_applications).update_node(
            update_manifestations)
        self.assertThat(updated, Equals(DeploymentState(nodes=[end_node])))

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
            applications={},
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
                    applications={},
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
                    applications={},
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

    def test_remove_existing_node(self):
        """
        If a ``NodeState`` exists, ``remove_node`` removes it.
        """
        node = NodeState(hostname=u"1.2.2.4", uuid=uuid4())
        another_node = NodeState(hostname=u"1.2.2.5", uuid=uuid4())
        original = DeploymentState(nodes=[node, another_node])
        self.assertEqual(DeploymentState(nodes=[node]),
                         original.remove_node(another_node.uuid))

    def test_remove_non_existing_node(self):
        """
        If a ``NodeState`` does exists, ``remove_node`` does nothing.
        """
        original = DeploymentState(
            nodes=[NodeState(hostname=u"1.2.2.4", uuid=uuid4())])
        self.assertEqual(original, original.remove_node(uuid4()))


class SameNodeTests(TestCase):
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


class NodeStateWipingTests(TestCase):
    """
    Tests for ``NodeState.get_information_wipe``.
    """
    NODE_FROM_APP_AGENT = NodeState(hostname=u"1.2.3.4", uuid=uuid4(),
                                    applications={APP1.name: APP1},
                                    manifestations=None,
                                    paths=None,
                                    devices=None)
    APP_WIPE = NODE_FROM_APP_AGENT.get_information_wipe()

    NODE_FROM_DATASET_AGENT = NodeState(hostname=NODE_FROM_APP_AGENT.hostname,
                                        uuid=NODE_FROM_APP_AGENT.uuid,
                                        applications=None,
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
        different_apps_node = self.NODE_FROM_APP_AGENT.set(applications={
            APP2.name: APP2})

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


class NoWipeTests(TestCase):
    """
    Tests for ``NoWipe``.
    """
    def test_interface(self):
        """
        ``NoWipe`` instances provide ``IClusterStateWipe``.
        """
        self.assertTrue(verifyObject(IClusterStateWipe, NoWipe()))

    def test_key_always_the_same(self):
        """
        A ``NoWipe`` always has the same key.
        """
        self.assertEqual(NoWipe().key(), NoWipe().key())

    def test_applying_does_nothing(self):
        """
        Applying the ``NoWipe`` does nothing to the cluster state.
        """
        non_manifest = NonManifestDatasets(datasets={MANIFESTATION.dataset_id:
                                                     MANIFESTATION.dataset})
        cluster_state = non_manifest.update_cluster_state(DeploymentState())

        # "Wiping" this information has no effect:
        updated = NoWipe().update_cluster_state(cluster_state)
        self.assertEqual(updated, cluster_state)


class NonManifestDatasetsWipingTests(TestCase):
    """
    Tests for ``NonManifestDatasets.get_information_wipe()``.

    See above for demonstration ``NoWipe`` has no side-effects.
    """
    def test_no_wipe(self):
        """
        Applying the ``IClusterStateWipe`` does nothing to the cluster state.
        """
        non_manifest = NonManifestDatasets(datasets={MANIFESTATION.dataset_id:
                                                     MANIFESTATION.dataset})
        wipe = non_manifest.get_information_wipe()
        self.assertIsInstance(wipe, NoWipe)


class LinkTests(TestCase):
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


class LeaseTests(TestCase):
    """
    Tests for ``Leases``.
    """
    def setUp(self):
        """
        Setup for each test.
        """
        super(LeaseTests, self).setUp()
        self.leases = Leases()
        self.now = datetime.datetime.now()
        self.dataset_id = uuid4()
        self.node_id = uuid4()
        self.dataset = Dataset(dataset_id=unicode(self.dataset_id))
        self.node = Node(uuid=self.node_id)
        self.lease_duration = 60 * 60

    def test_lease_expiry_datetime(self):
        """
        An lease has an expiry date/time after the specified number
        of seconds from the time of acquisition.
        """
        expected_expiration = self.now + datetime.timedelta(
            seconds=self.lease_duration)
        leases = self.leases.acquire(
            self.now, self.dataset_id, self.node_id, self.lease_duration
        )
        lease = leases.get(self.dataset_id)
        self.assertEqual(lease.expiration, expected_expiration)

    def test_indefinite_lease(self):
        """
        An acquired lease can be set to never expire.
        """
        leases = self.leases.acquire(self.now, self.dataset_id, self.node_id)
        lease = leases.get(self.dataset_id)
        self.assertIsNone(lease.expiration)

    def test_lease_expires(self):
        """
        An acquired lease expires after the specified number of seconds and
        is removed from the ``Leases`` map.
        """
        leases = self.leases.acquire(
            self.now, self.dataset_id, self.node_id, self.lease_duration
        )
        # Assert the lease has been acquired successfully.
        self.assertIn(self.dataset_id, leases)
        # Fake a time the first lease has expired.
        now = self.now + datetime.timedelta(seconds=self.lease_duration + 1)
        leases = leases.expire(now)
        # Assert the lease has been removed successfully.
        self.assertNotIn(self.dataset_id, leases)

    def test_indefinite_lease_never_expires(self):
        """
        An acquired lease set to never expire is not removed from ``Leases``
        map.
        """
        leases = self.leases.acquire(self.now, self.dataset_id, self.node_id)
        self.assertIn(self.dataset_id, leases)
        now = self.now + datetime.timedelta(seconds=self.lease_duration)
        leases = leases.expire(now)
        self.assertIn(self.dataset_id, leases)

    def test_lease_renewable(self):
        """
        A lease that is renewed is updated in the Leases map with its new
        expiry date/time.
        """
        # Acquire a lease on a node with an expiration time.
        leases = self.leases.acquire(
            self.now, self.dataset_id, self.node_id, self.lease_duration
        )
        # Assert that the lease has the expected expiration time.
        expected_expiration = self.now + datetime.timedelta(
            seconds=self.lease_duration)
        lease = leases.get(self.dataset_id)
        self.assertEqual(lease.expiration, expected_expiration)
        # Acquire the same lease with a different expiration time.
        leases = leases.acquire(
            self.now, self.dataset_id, self.node_id, self.lease_duration * 2
        )
        # Assert the lease's expiration time has been updated.
        new_expected_expiration = self.now + datetime.timedelta(
            seconds=self.lease_duration * 2)
        lease = leases.get(self.dataset_id)
        self.assertEqual(lease.expiration, new_expected_expiration)

    def test_lease_release(self):
        """
        A lease that has been released is removed from the Leases map.
        """
        # Acquire a lease.
        leases = self.leases.acquire(self.now, self.dataset_id, self.node_id)
        # Assert the lease was acquired successfully.
        self.assertIn(self.dataset_id, leases)
        # Release the lease.
        leases = leases.release(self.dataset_id, self.node_id)
        # Assert the lease has been released successfully.
        self.assertNotIn(self.dataset_id, leases)

    def test_error_on_release_lease_held_by_other_node(self):
        """
        A ``LeaseReleaseError`` is raised when attempting to release a lease
        held by another node.
        """
        # Acquire a lease on a node
        leases = self.leases.acquire(
            self.now, self.dataset_id, self.node_id, self.lease_duration)
        # Create a second node
        node2 = Node(uuid=uuid4())
        # Attempt to release a lease on node2 for the existing dataset
        exception = self.assertRaises(
            LeaseError, leases.release,
            self.dataset_id, node2.uuid
        )
        expected_error = (
            u"Cannot release lease {} for node {}: "
            u"Lease already held by another node".format(
                unicode(self.dataset_id), unicode(node2.uuid)
            )
        )
        self.assertEqual(
            exception.message, expected_error
        )

    def test_error_on_acquire_lease_held_by_other_node(self):
        """
        A ``LeaseAcquisitionError`` is raised when attempting to acquire
        a lease held by another node.
        """
        # Acquire a lease on a node
        leases = self.leases.acquire(self.now, self.dataset_id, self.node_id)
        # Create a second node
        node2 = Node(uuid=uuid4())
        # Attempt to acquire the lease for node2 for the existing dataset
        exception = self.assertRaises(
            LeaseError, leases.acquire,
            self.now, self.dataset_id, node2.uuid
        )
        expected_error = (
            u"Cannot acquire lease " + unicode(self.dataset_id) +
            u" for node " + unicode(node2.uuid) +
            u": Lease already held by another node"
        )
        self.assertEqual(
            exception.message, expected_error
        )

    def test_invariant_success(self):
        """
        A lease's ID (key in the ``Leases`` map) must match its dataset ID.
        """
        lease = Lease(
            dataset_id=self.dataset_id, node_id=self.node_id, expiration=None
        )
        # This test's "assertion" is that this does not raise an exception.
        self.leases.set(self.dataset_id, lease)

    def test_invariant_fail(self):
        """
        An ``InvariantException`` is raised if a lease's ID (key in the
        ``Leases`` map) does not match its dataset ID.
        """
        lease = Lease(
            dataset_id=self.dataset_id, node_id=self.node_id, expiration=None
        )
        # Try to map this lease to a different UUID.
        self.assertRaises(
            InvariantException,
            self.leases.set, uuid4(), lease
        )


class UpdateNodeStateEraTests(TestCase):
    """
    Tests for ``UpdateNodeStateEraTests``.
    """
    KNOWN_STATE = NodeState(hostname=u"1.1.1.1", uuid=uuid4())
    INITIAL_CLUSTER = DeploymentState(
        nodes=[KNOWN_STATE],
        node_uuid_to_era={KNOWN_STATE.uuid: uuid4()})
    NODE_STATE = NodeState(hostname=u"1.2.3.4",
                           uuid=uuid4(),
                           applications=None,
                           manifestations={},
                           devices={}, paths={})
    UPDATE_ERA_1 = UpdateNodeStateEra(uuid=NODE_STATE.uuid, era=uuid4())
    UPDATE_ERA_2 = UpdateNodeStateEra(uuid=NODE_STATE.uuid, era=uuid4())

    def test_iclusterstatechange(self):
        """
        ``UpdateNodeStateEra`` instances provide ``IClusterStateChange``.
        """
        self.assertTrue(verifyObject(IClusterStateChange, self.UPDATE_ERA_1))

    def test_get_information_wipe(self):
        """
        ``UpdateNodeStateEra`` has no side-effects from wiping.
        """
        self.assertIsInstance(self.UPDATE_ERA_1.get_information_wipe(), NoWipe)

    def test_no_era(self):
        """
        If era information was not known, ``UpdateNodeStateEra`` adds it.
        """
        state = self.UPDATE_ERA_1.update_cluster_state(self.INITIAL_CLUSTER)
        self.assertEqual(
            state,
            self.INITIAL_CLUSTER.transform(
                ["node_uuid_to_era", self.UPDATE_ERA_1.uuid],
                self.UPDATE_ERA_1.era))

    def test_same_era(self):
        """
        If the known era matches, ``UpdateNodeStateEra`` does nothing.
        """
        state = self.UPDATE_ERA_1.update_cluster_state(self.INITIAL_CLUSTER)
        state = self.NODE_STATE.update_cluster_state(state)

        updated_state = self.UPDATE_ERA_1.update_cluster_state(state)
        self.assertEqual(state, updated_state)

    def test_different_era(self):
        """
        If the era differs, it is updated.
        """
        state = self.UPDATE_ERA_1.update_cluster_state(self.INITIAL_CLUSTER)

        updated_state = self.UPDATE_ERA_2.update_cluster_state(state)
        self.assertEqual(
            updated_state,
            self.UPDATE_ERA_2.update_cluster_state(self.INITIAL_CLUSTER))

    def test_different_era_discards_state(self):
        """
        If the era differs the corresponding ``NodeState`` is removed.
        """
        state = self.UPDATE_ERA_1.update_cluster_state(self.INITIAL_CLUSTER)
        state = self.NODE_STATE.update_cluster_state(state)

        updated_state = self.UPDATE_ERA_2.update_cluster_state(state)
        self.assertEqual(
            updated_state,
            self.UPDATE_ERA_2.update_cluster_state(self.INITIAL_CLUSTER))
