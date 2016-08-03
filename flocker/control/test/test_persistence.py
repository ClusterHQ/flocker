# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.control._persistence``.
"""
import json
import string

from datetime import datetime, timedelta
from uuid import uuid4, UUID

from pytz import UTC

from eliot.testing import (
    assertHasMessage,
    assertHasAction,
    capture_logging
)

from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.datetime import datetimes

from twisted.internet import reactor
from twisted.internet.task import Clock
from twisted.python.filepath import FilePath

from pyrsistent import PClass, pset

from testtools.matchers import Is, Equals, Not

from ..testtools import deployment_strategy, arbitrary_transformation

from ...testtools import AsyncTestCase, TestCase
from .._persistence import (
    ConfigurationPersistenceService, wire_decode, wire_encode,
    _LOG_SAVE, _LOG_STARTUP, migrate_configuration,
    _CONFIG_VERSION, ConfigurationMigration, ConfigurationMigrationError,
    _LOG_UPGRADE, MissingMigrationError, update_leases, _LOG_EXPIRE,
    _LOG_UNCHANGED_DEPLOYMENT_NOT_SAVED, to_unserialized_json, generation_hash
    )
from .._model import (
    Deployment, Application, DockerImage, Node, Dataset, Manifestation,
    AttachedVolume, SERIALIZABLE_CLASSES, NodeState, Configuration,
    Port, Link, Leases, Lease, BlockDeviceOwnership, PersistentState,
    )

# The UUID values for the Dataset and Node in the following TEST_DEPLOYMENTs
# match those in the versioned JSON configuration files used by tests in this
# module.  If these values are changed, you will also need to regenerate the
# test JSON files using the scripts provided in the
# flocker/control/test/configurations/ directory, using the correct commit
# checkout to generate JSON appropriate to each config version.
DATASET = Dataset(dataset_id=u'4e7e3241-0ec3-4df6-9e7c-3f7e75e08855',
                  metadata={u"name": u"myapp"})
NODE_UUID = UUID(u'ab294ce4-a6c3-40cb-a0a2-484a1f09521c')
MANIFESTATION = Manifestation(dataset=DATASET, primary=True)
TEST_DEPLOYMENT_1 = Deployment(
    leases=Leases(),
    nodes=[Node(uuid=NODE_UUID,
                applications={
                    u'myapp':
                    Application(
                        name=u'myapp',
                        image=DockerImage.from_string(u'postgresql:7.6'),
                        volume=AttachedVolume(
                            manifestation=MANIFESTATION,
                            mountpoint=FilePath(b"/xxx/yyy"))
                    )
                },
                manifestations={DATASET.dataset_id: MANIFESTATION})],
)
TEST_DEPLOYMENT_2 = TEST_DEPLOYMENT_1.set(
    'persistent_state', PersistentState(
        blockdevice_ownership=BlockDeviceOwnership({
            UUID(u'b229d949-0856-4011-96e5-3dd0a5586180'): u'block-device-id',
        })
    )
)
TEST_DEPLOYMENTS = [
    TEST_DEPLOYMENT_1,
    TEST_DEPLOYMENT_2
]
LATEST_TEST_DEPLOYMENT = TEST_DEPLOYMENTS[-1]


V1_TEST_DEPLOYMENT_JSON = FilePath(__file__).sibling(
    'configurations').child(b"configuration_1_v1.json").getContent()


class LeasesTests(AsyncTestCase):
    """
    Tests for ``LeaseService`` and ``update_leases``.
    """
    def setUp(self):
        super(LeasesTests, self).setUp()
        self.clock = Clock()
        self.persistence_service = ConfigurationPersistenceService(
            reactor=self.clock,
        )
        self.persistence_service.startService()
        self.addCleanup(self.persistence_service.stopService)

    def test_update_leases_saves_changed_leases(self):
        """
        ``update_leases`` only changes the leases stored in the configuration.
        """
        node_id = uuid4()
        dataset_id = uuid4()

        original_leases = Leases().acquire(
            datetime.fromtimestamp(0, UTC), uuid4(), node_id)

        def update(leases):
            return leases.acquire(
                datetime.fromtimestamp(1000, UTC), dataset_id, node_id)

        d = self.persistence_service.save(
            LATEST_TEST_DEPLOYMENT.set(leases=original_leases))
        d.addCallback(
            lambda _: update_leases(update, self.persistence_service))

        def updated(_):
            self.assertEqual(
                self.persistence_service.get(),
                LATEST_TEST_DEPLOYMENT.set(leases=update(original_leases)))
        d.addCallback(updated)
        return d

    def test_update_leases_result(self):
        """
        ``update_leases`` returns a ``Deferred`` firing with the updated
        ``Leases`` instance.
        """
        node_id = uuid4()
        dataset_id = uuid4()
        original_leases = Leases()

        def update(leases):
            return leases.acquire(
                datetime.fromtimestamp(1000, UTC), dataset_id, node_id)
        d = update_leases(update, self.persistence_service)

        def updated(updated_leases):
            self.assertEqual(updated_leases, update(original_leases))
        d.addCallback(updated)
        return d

    def test_expired_lease_removed(self):
        """
        A lease that has expired is removed from the persisted
        configuration.
        """
        timestep = 100
        node_id = uuid4()
        ids = uuid4(), uuid4()
        # First dataset lease expires at timestep:
        now = self.clock.seconds()
        leases = Leases().acquire(
            datetime.fromtimestamp(now, UTC), ids[0], node_id, timestep)
        # Second dataset lease expires at timestep * 2:
        leases = leases.acquire(
            datetime.fromtimestamp(now, UTC), ids[1], node_id, timestep * 2)
        new_config = Deployment(leases=leases)
        d = self.persistence_service.save(new_config)

        def saved(_):
            self.clock.advance(timestep - 1)  # 99
            before_first_expire = self.persistence_service.get().leases
            self.clock.advance(2)  # 101
            after_first_expire = self.persistence_service.get().leases
            self.clock.advance(timestep - 2)  # 199
            before_second_expire = self.persistence_service.get().leases
            self.clock.advance(2)  # 201
            after_second_expire = self.persistence_service.get().leases

            self.assertTupleEqual(
                (before_first_expire, after_first_expire,
                 before_second_expire, after_second_expire),
                (leases, leases.remove(ids[0]), leases.remove(ids[0]),
                 leases.remove(ids[0]).remove(ids[1])))
        d.addCallback(saved)
        return d

    @capture_logging(None)
    def test_expire_lease_logging(self, logger):
        """
        An expired lease is logged.
        """
        node_id = uuid4()
        dataset_id = uuid4()
        leases = Leases().acquire(
            datetime.fromtimestamp(self.clock.seconds(), UTC),
            dataset_id, node_id, 1)

        d = self.persistence_service.save(Deployment(leases=leases))

        def saved(_):
            logger.reset()
            self.clock.advance(1000)
            assertHasMessage(self, logger, _LOG_EXPIRE, {
                u"dataset_id": dataset_id, u"node_id": node_id})
        d.addCallback(saved)
        return d


class ConfigurationPersistenceServiceTests(AsyncTestCase):
    """
    Tests for ``ConfigurationPersistenceService``.
    """
    def service(self, path):
        """
        Start a service, schedule its stop.

        :param FilePath path: Where to store data.
        :param logger: Optional eliot ``Logger`` to set before startup.

        :return: Started ``ConfigurationPersistenceService``.
        """
        service = ConfigurationPersistenceService.from_directory(
            reactor=reactor,
            directory=path,
        )
        service.startService()
        self.addCleanup(service.stopService)
        return service

    def test_empty_on_start(self):
        """
        If no configuration was previously saved, starting a service results
        in an empty ``Deployment``.
        """
        service = self.service(FilePath(self.mktemp()))
        self.assertEqual(service.get(), Deployment(nodes=frozenset()))

    def test_directory_is_created(self):
        """
        If a directory does not exist in given path, it is created.
        """
        path = FilePath(self.mktemp())
        self.service(path)
        self.assertTrue(path.isdir())

    def test_file_is_created(self):
        """
        If no configuration file exists in the given path, it is created.
        """
        path = FilePath(self.mktemp())
        self.service(path)
        self.assertTrue(path.child(b"current_configuration.json").exists())

    @capture_logging(assertHasAction, _LOG_UPGRADE, succeeded=True,
                     startFields=dict(configuration=V1_TEST_DEPLOYMENT_JSON,
                                      source_version=1,
                                      target_version=_CONFIG_VERSION))
    def test_v1_file_creates_updated_file(self, logger):
        """
        If a version 1 configuration file exists under name
        current_configuration.v1.json, a new configuration file is
        created with the >v1 naming convention, current_configuration.json
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        v1_config_file = path.child(b"current_configuration.v1.json")
        v1_config_file.setContent(V1_TEST_DEPLOYMENT_JSON)
        self.service(path)
        self.assertTrue(path.child(b"current_configuration.json").exists())

    @capture_logging(assertHasAction, _LOG_UPGRADE, succeeded=True,
                     startFields=dict(configuration=V1_TEST_DEPLOYMENT_JSON,
                                      source_version=1,
                                      target_version=_CONFIG_VERSION))
    def test_v1_file_archived(self, logger):
        """
        If a version 1 configuration file exists, it is archived with a
        new name current_configuration.v1.old.json after upgrading.
        The original file name no longer exists.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        v1_config_file = path.child(b"current_configuration.v1.json")
        v1_config_file.setContent(V1_TEST_DEPLOYMENT_JSON)
        self.service(path)
        self.assertEqual(
            (True, False),
            (
                path.child(b"current_configuration.v1.old.json").exists(),
                path.child(b"current_configuration.v1.json").exists(),
            )
        )

    def test_old_configuration_is_upgraded(self):
        """
        The persistence service will detect if an existing configuration
        saved in a file is a previous version and perform a migration to
        the latest version.

        XXX: The upgraded configuration is not persisted immediately.  Only
        when the deployment is first saved and only if the deployment has
        changed. I'm not sure I like this -RichardW.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        v1_config_file = path.child(b"current_configuration.v1.json")
        v1_config_file.setContent(V1_TEST_DEPLOYMENT_JSON)
        config_path = path.child(b"current_configuration.json")
        service = self.service(path)
        upgraded_deployment = service.get()
        changed_upgraded_deployment = arbitrary_transformation(
            upgraded_deployment
        )
        d = service.save(changed_upgraded_deployment)

        def check_file(ignored):
            configuration = wire_decode(config_path.getContent())
            self.assertEqual(configuration.version, _CONFIG_VERSION)
        d.addCallback(check_file)
        return d

    def test_current_configuration_unchanged(self):
        """
        A persisted configuration saved in the latest configuration
        version is not upgraded and therefore remains unchanged on
        service startup.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        config_path = path.child(b"current_configuration.json")
        persisted_configuration = Configuration(
            version=_CONFIG_VERSION, deployment=LATEST_TEST_DEPLOYMENT)
        config_path.setContent(wire_encode(persisted_configuration))
        self.service(path)
        loaded_configuration = wire_decode(config_path.getContent())
        self.assertEqual(loaded_configuration, persisted_configuration)

    @capture_logging(assertHasAction, _LOG_SAVE, succeeded=True,
                     startFields=dict(configuration=LATEST_TEST_DEPLOYMENT))
    def test_save_then_get(self, logger):
        """
        A configuration that was saved can subsequently retrieved.
        """
        service = self.service(FilePath(self.mktemp()))
        d = service.save(LATEST_TEST_DEPLOYMENT)
        d.addCallback(lambda _: service.get())
        d.addCallback(self.assertEqual, LATEST_TEST_DEPLOYMENT)
        return d

    @capture_logging(assertHasMessage, _LOG_STARTUP,
                     fields=dict(configuration=LATEST_TEST_DEPLOYMENT))
    def test_persist_across_restarts(self, logger):
        """
        A configuration that was saved can be loaded from a new service.
        """
        path = FilePath(self.mktemp())
        service = ConfigurationPersistenceService.from_directory(
            reactor, path
        )
        service.startService()
        logger.reset()
        d = service.save(LATEST_TEST_DEPLOYMENT)
        d.addCallback(lambda _: service.stopService())

        def retrieve_in_new_service(_):
            new_service = self.service(path)
            self.assertEqual(new_service.get(), LATEST_TEST_DEPLOYMENT)
        d.addCallback(retrieve_in_new_service)
        return d

    def test_register_for_callback(self):
        """
        Callbacks can be registered that are called every time there is a
        change saved.
        """
        service = self.service(FilePath(self.mktemp()))
        callbacks = []
        callbacks2 = []
        service.register(lambda: callbacks.append(1))
        d = service.save(LATEST_TEST_DEPLOYMENT)

        def saved(_):
            service.register(lambda: callbacks2.append(1))
            uuid = uuid4()
            changed = LATEST_TEST_DEPLOYMENT.transform(
                ("nodes", uuid), Node(uuid=uuid),
            )
            return service.save(changed)
        d.addCallback(saved)

        def saved_again(_):
            self.assertEqual((callbacks, callbacks2), ([1, 1], [1]))
        d.addCallback(saved_again)
        return d

    @capture_logging(
        lambda test, logger:
        test.assertEqual(len(logger.flush_tracebacks(ZeroDivisionError)), 1))
    def test_register_for_callback_failure(self, logger):
        """
        Failed callbacks don't prevent later callbacks from being called.
        """
        service = self.service(FilePath(self.mktemp()))
        callbacks = []
        service.register(lambda: 1/0)
        service.register(lambda: callbacks.append(1))
        d = service.save(LATEST_TEST_DEPLOYMENT)

        def saved(_):
            self.assertEqual(callbacks, [1])
        d.addCallback(saved)
        return d

    @capture_logging(assertHasMessage, _LOG_UNCHANGED_DEPLOYMENT_NOT_SAVED)
    def test_callback_not_called_for_unchanged_deployment(self, logger):
        """
        If the old deployment and the new deployment are equivalent, registered
        callbacks are not called.
        """
        service = self.service(FilePath(self.mktemp()))

        state = []

        def callback():
            state.append(None)

        saving = service.save(LATEST_TEST_DEPLOYMENT)

        def saved_old(ignored):
            service.register(callback)
            return service.save(LATEST_TEST_DEPLOYMENT)

        saving.addCallback(saved_old)

        def saved_new(ignored):
            self.assertEqual(
                [], state,
                "Registered callback was called; should not have been."
            )

        saving.addCallback(saved_new)
        return saving

    def test_success_returned_for_unchanged_deployment(self):
        """
        ``save`` returns a ``Deferred`` that fires with ``None`` when called
        with a deployment that is the same as the already-saved deployment.
        """
        service = self.service(FilePath(self.mktemp()))

        old_saving = service.save(LATEST_TEST_DEPLOYMENT)

        def saved_old(ignored):
            new_saving = service.save(LATEST_TEST_DEPLOYMENT)
            new_saving.addCallback(self.assertEqual, None)
            return new_saving

        old_saving.addCallback(saved_old)
        return old_saving

    def get_hash(self, service):
        """
        Get the configuration, doing some sanity checks along the way.

        :param service: A ``ConfigurationPersistenceService``.
        :return: Result of ``service.configuration_hash()``.
        """
        # Repeatable:
        result1 = service.configuration_hash()
        result2 = service.configuration_hash()
        self.assertEqual(result1, result2)
        # Bytes:
        self.assertIsInstance(result1, bytes)
        return result1

    def test_hash_on_startup(self):
        """
        An empty configuration can be hashed.
        """
        path = FilePath(self.mktemp())
        service = ConfigurationPersistenceService.from_directory(
            reactor, path
        )
        service.startService()
        self.addCleanup(service.stopService)

        # Hash can be retrieved and passes sanity check:
        self.get_hash(service)

    def test_hash_on_save(self):
        """
        The configuration hash changes when a new version is saved.
        """
        path = FilePath(self.mktemp())
        service = ConfigurationPersistenceService.from_directory(
            reactor, path
        )
        service.startService()
        self.addCleanup(service.stopService)
        original = self.get_hash(service)
        d = service.save(LATEST_TEST_DEPLOYMENT)

        def saved(_):
            updated = self.get_hash(service)
            self.assertNotEqual(updated, original)
        d.addCallback(saved)
        return d

    def test_hash_persists_across_restarts(self):
        """
        A configuration that was saved can be loaded from a new service.
        """
        path = FilePath(self.mktemp())
        service = ConfigurationPersistenceService.from_directory(
            reactor, path
        )
        service.startService()
        self.addCleanup(service.stopService)
        d = service.save(LATEST_TEST_DEPLOYMENT)

        def saved(_):
            original = self.get_hash(service)
            service.stopService()
            service.startService()
            self.assertEqual(self.get_hash(service), original)
        d.addCallback(saved)
        return d


class StubMigration(object):
    """
    A simple stub migration class, used to test ``migrate_configuration``.
    These upgrade methods are not concerned with manipulating the input
    configurations; they are used simply to ensure ``migrate_configuration``
    follows the correct sequence of method calls to upgrade from version X
    to version Y.
    """
    @classmethod
    def upgrade_from_v1(cls, config):
        config = json.loads(config)
        if config['version'] != 1:
            raise ConfigurationMigrationError(
                "Supplied configuration was not a valid v1 config."
            )
        return json.dumps({"version": 2, "configuration": "fake"})

    @classmethod
    def upgrade_from_v2(cls, config):
        config = json.loads(config)
        if config['version'] != 2:
            raise ConfigurationMigrationError(
                "Supplied configuration was not a valid v2 config."
            )
        return json.dumps({"version": 3, "configuration": "fake"})


class MigrateConfigurationTests(TestCase):
    """
    Tests for ``migrate_configuration``.
    """
    v1_config = json.dumps({"version": 1})

    def test_error_on_undefined_migration_path(self):
        """
        A ``MissingMigrationError`` is raised if a migration path
        from one version to another cannot be found in the supplied
        migration class.
        """
        e = self.assertRaises(
            MissingMigrationError,
            migrate_configuration, 1, 4, self.v1_config, StubMigration
        )
        expected_error = (
            u'Unable to find a migration path for a version 3 to '
            u'version 4 configuration. No migration method '
            u'upgrade_from_v3 could be found.'
        )
        self.assertEqual(e.message, expected_error)

    def test_sequential_migrations(self):
        """
        A migration from one configuration version to another will
        sequentially perform all necessary upgrades, e.g. v1 to v2 followed
        by v2 to v3.
        """
        # Get a valid v2 config.
        v2_config = migrate_configuration(1, 2, self.v1_config, StubMigration)
        # Perform two sequential migrations to get from v1 to v3, starting
        # with a v1 config.
        result = migrate_configuration(1, 3, self.v1_config, StubMigration)
        # Compare the v1 --> v3 upgrade to the direct result of the
        # v2 --> v3 upgrade on the v2 config, Both should be identical
        # and valid v3 configs.
        self.assertEqual(result, StubMigration.upgrade_from_v2(v2_config))


DATASETS = st.builds(
    Dataset,
    dataset_id=st.uuids(),
    maximum_size=st.integers(min_value=1),
)

# UTC `datetime`s accurate to seconds
DATETIMES_TO_SECONDS = datetimes(
    timezones=['UTC']
).map(
    lambda d: d.replace(microsecond=0)
)

LEASES = st.builds(
    Lease,
    dataset_id=st.uuids(),
    node_id=st.uuids(),
    expiration=st.one_of(
        st.none(),
        DATETIMES_TO_SECONDS
    )
)

# Constrain primary to be True so that we don't get invariant errors from Node
# due to having two differing manifestations of the same dataset id.
MANIFESTATIONS = st.builds(
    Manifestation, primary=st.just(True), dataset=DATASETS)
IMAGES = st.builds(
    DockerImage,
    tag=st.text(alphabet=string.letters, min_size=1),
    repository=st.text(alphabet=string.letters, min_size=1),
)
NONE_OR_INT = st.one_of(
    st.none(),
    st.integers(min_value=0)
)
ST_PORTS = st.integers(min_value=1, max_value=65535)
PORTS = st.builds(
    Port,
    internal_port=ST_PORTS,
    external_port=ST_PORTS
)
LINKS = st.builds(
    Link,
    local_port=ST_PORTS,
    remote_port=ST_PORTS,
    alias=st.text(alphabet=string.letters, min_size=1)
)
FILEPATHS = st.text(alphabet=string.printable).map(FilePath)
VOLUMES = st.builds(
    AttachedVolume, manifestation=MANIFESTATIONS, mountpoint=FILEPATHS)
APPLICATIONS = st.builds(
    Application, name=st.text(), image=IMAGES,
    # A MemoryError will likely occur without the max_size limits on
    # Ports and Links. The max_size value that will trigger memory errors
    # will vary system to system. 5 is a reasonable test range for realistic
    # container usage that should also not run out of memory on most modern
    # systems.
    ports=st.sets(PORTS, max_size=5),
    links=st.sets(LINKS, max_size=5),
    volume=st.none() | VOLUMES,
    environment=st.dictionaries(keys=st.text(), values=st.text()),
    memory_limit=NONE_OR_INT,
    cpu_shares=NONE_OR_INT,
    running=st.booleans(),
    swappiness=st.integers(min_value=0, max_value=100)
)


def _build_node(applications):
    # All the manifestations in `applications`.
    app_manifestations = set(
        app.volume.manifestation for app in applications if app.volume
    )
    # A set that contains all of those, plus an arbitrary set of
    # manifestations.
    dataset_ids = frozenset(
        app.volume.manifestation.dataset_id
        for app in applications if app.volume
    )
    manifestations = (
        st.sets(MANIFESTATIONS.filter(
            lambda m: m.dataset_id not in dataset_ids))
        .map(pset)
        .map(lambda ms: ms.union(app_manifestations))
        .map(lambda ms: dict((m.dataset.dataset_id, m) for m in ms)))
    return st.builds(
        Node, uuid=st.uuids(),
        applications=st.just({a.name: a for a in applications}),
        manifestations=manifestations)


NODES = st.lists(
    APPLICATIONS,
    # If we add this hint on the number of applications, Hypothesis is able to
    # run many more tests.
    average_size=2,
    unique_by=lambda app:
    app if not app.volume else app.volume.manifestation.dataset_id).map(
        pset).flatmap(_build_node)


BLOCKDEVICE_OWNERSHIP = st.builds(
    BlockDeviceOwnership,
    st.dictionaries(keys=st.uuids(), values=st.text()),
)

PERSISTENT_STATES = st.builds(
    PersistentState,
    blockdevice_ownership=BLOCKDEVICE_OWNERSHIP,
)

DEPLOYMENTS = st.builds(
    # If we leave the number of nodes unbounded, Hypothesis will take too long
    # to build examples, causing intermittent timeouts. Making it roughly 2
    # should give us adequate test coverage.
    Deployment, nodes=st.sets(NODES, average_size=2),
    leases=st.sets(LEASES, average_size=2).map(
        lambda ls: dict((l.dataset_id, l) for l in ls)),
    persistent_state=PERSISTENT_STATES,
)


SUPPORTED_VERSIONS = st.integers(1, _CONFIG_VERSION)


class WireEncodeDecodeTests(TestCase):
    """
    Tests for ``to_unserialized_json``, ``wire_encode`` and ``wire_decode``.
    """
    def test_encode_to_bytes(self):
        """
        ``wire_encode`` converts the given object to ``bytes``.
        """
        self.assertIsInstance(wire_encode(LATEST_TEST_DEPLOYMENT), bytes)

    @given(DEPLOYMENTS)
    def test_roundtrip(self, deployment):
        """
        A range of generated configurations (deployments) can be
        roundtripped via the wire encode/decode.
        """
        source_json = wire_encode(deployment)
        decoded_deployment = wire_decode(source_json)
        self.assertEqual(decoded_deployment, deployment)

    @given(DEPLOYMENTS)
    def test_to_unserialized_json(self, deployment):
        """
        ``to_unserialized_json`` is same output as ``wire_encode`` except
        without doing JSON byte encoding.
        """
        unserialized = to_unserialized_json(deployment)
        self.assertEquals(wire_decode(json.dumps(unserialized)), deployment)

    def test_no_arbitrary_decoding(self):
        """
        ``wire_decode`` will not decode classes that are not in
        ``SERIALIZABLE_CLASSES``.
        """
        class Temp(PClass):
            """A class."""
        SERIALIZABLE_CLASSES.append(Temp)

        def cleanup():
            if Temp in SERIALIZABLE_CLASSES:
                SERIALIZABLE_CLASSES.remove(Temp)
        self.addCleanup(cleanup)

        data = wire_encode(Temp())
        SERIALIZABLE_CLASSES.remove(Temp)
        # Possibly future versions might throw exception, the key point is
        # that the returned object is not a Temp instance.
        self.assertFalse(isinstance(wire_decode(data), Temp))

    def test_complex_keys(self):
        """
        Objects with attributes that are ``PMap``\s with complex keys
        (i.e. not strings) can be roundtripped.
        """
        node_state = NodeState(hostname=u'127.0.0.1', uuid=uuid4(),
                               manifestations={}, paths={},
                               devices={uuid4(): FilePath(b"/tmp")})
        self.assertEqual(node_state, wire_decode(wire_encode(node_state)))

    def test_datetime(self):
        """
        A datetime with a timezone can be roundtripped (with potential loss of
        less-than-second resolution).
        """
        dt = datetime.now(tz=UTC)
        self.assertTrue(
            abs(wire_decode(wire_encode(dt)) - dt) < timedelta(seconds=1))

    def test_naive_datetime(self):
        """
        A naive datetime will fail. Don't use those, always use an explicit
        timezone.
        """
        self.assertRaises(ValueError, wire_encode, datetime.now())


class ConfigurationMigrationTests(TestCase):
    """
    Tests for ``ConfigurationMigration`` class that performs individual
    configuration upgrades.
    """
    @given(st.tuples(SUPPORTED_VERSIONS, SUPPORTED_VERSIONS).map(
        lambda x: tuple(sorted(x))))
    def test_upgrade_configuration_versions(self, versions):
        """
        A range of versions can be upgraded and the configuration
        blob after upgrade will match that which is expected for the
        particular version.

        See flocker/control/test/configurations for individual
        version JSON files and generation code.
        """
        source_version, target_version = versions
        configs_dir = FilePath(__file__).sibling('configurations')

        # Choose the latest configuration number available for the given
        # version of the config. The configuration has increased in complexity
        # over time, so we have added additional configurations to verify that
        # the new fields can be correctly upgraded.
        source_json_glob = b"configuration_*_v%d.json" % source_version
        source_jsons = sorted(configs_dir.globChildren(source_json_glob),
                              key=lambda x: x.basename())
        config_num = int(source_jsons[-1].basename().split('_')[1])

        source_json_file = b"configuration_%d_v%d.json" % (config_num,
                                                           versions[0])
        target_json_file = b"configuration_%d_v%d.json" % (config_num,
                                                           versions[1])
        source_json = configs_dir.child(source_json_file).getContent()
        target_json = configs_dir.child(target_json_file).getContent()
        upgraded_json = migrate_configuration(
            source_version, target_version,
            source_json, ConfigurationMigration)
        self.assertEqual(json.loads(upgraded_json), json.loads(target_json))


class LatestGoldenFilesValid(TestCase):
    """
    Tests for the latest golden files to ensure they have not regressed.
    """

    def test_can_create_latest_golden(self):
        """
        The latest golden files should be identical to ones generated from
        HEAD.
        """
        configs_dir = FilePath(__file__).sibling('configurations')
        for i, deployment in enumerate(TEST_DEPLOYMENTS, start=1):
            encoding = wire_encode(
                Configuration(version=_CONFIG_VERSION, deployment=deployment)
            )
            path = configs_dir.child(
                b"configuration_%d_v%d.json" % (i, _CONFIG_VERSION)
            )
            self.assertEqual(
                encoding, path.getContent().rstrip(),
                "Golden test file %s can not be generated from HEAD. Please "
                "review the python files in that directory to re-generate "
                "that file if you have intentionally changed the backing test "
                "data. You might need to update the model version and write "
                "an upgrade test if you are intentionally changing the "
                "model." % (path.path,)
            )


class GenerationHashTests(TestCase):
    """
    Tests for generation_hash.
    """

    @given(st.data())
    def test_no_hash_collisions(self, data):
        """
        Hashes of different deployments do not have hash collisions, hashes of
        the same object have the same hash.
        """
        # With 128 bits of hash, a collision here indicates a fault in the
        # algorithm.

        # Generate the first deployment.
        deployment_a = data.draw(deployment_strategy())

        # Decide if we want to generate a second deployment, or just compare
        # the first deployment to a re-serialized version of itself:
        simple_comparison = data.draw(st.booleans())
        if simple_comparison:
            deployment_b = wire_decode(wire_encode(deployment_a))
        else:
            deployment_b = data.draw(deployment_strategy())

        should_be_equal = (deployment_a == deployment_b)
        if simple_comparison:
            self.assertThat(
                should_be_equal,
                Is(True)
            )

        hash_a = generation_hash(deployment_a)
        hash_b = generation_hash(deployment_b)

        if should_be_equal:
            self.assertThat(
                hash_a,
                Equals(hash_b)
            )
        else:
            self.assertThat(
                hash_a,
                Not(Equals(hash_b))
            )

    def test_maps_and_sets_differ(self):
        """
        Mappings hash to different values than frozensets of their iteritems().
        """
        self.assertThat(
            generation_hash(frozenset([('a', 1), ('b', 2)])),
            Not(Equals(generation_hash(dict(a=1, b=2))))
        )

    def test_strings_and_jsonable_types_differ(self):
        """
        Strings and integers hash to different values.
        """
        self.assertThat(
            generation_hash(5),
            Not(Equals(generation_hash('5')))
        )

    def test_sets_and_objects_differ(self):
        """
        Sets can be hashed and 1 element sets have a different hash than the
        hash of the single element.
        """
        self.assertThat(
            generation_hash(5),
            Not(Equals(generation_hash(frozenset([5]))))
        )

    def test_lists_and_objects_differ(self):
        """
        Lists can be hashed, and have a different hash value than scalars with
        the same value or sets with the same values.
        """
        self.assertThat(
            generation_hash(913),
            Not(Equals(generation_hash([913])))
        )
        self.assertThat(
            generation_hash(frozenset([913])),
            Not(Equals(generation_hash([913])))
        )

    def test_empty_sets_can_be_hashed(self):
        """
        Empty sets can be hashed and result in different hashes than empty
        strings or the string 'NULLSET'.
        """
        self.assertThat(
            generation_hash(frozenset()),
            Not(Equals(generation_hash('')))
        )
        self.assertThat(
            generation_hash(frozenset()),
            Not(Equals(generation_hash(b'NULLSET')))
        )

    def test_unicode_hash(self):
        """
        Unicode strings can be hashed, and are hashed to the same value as
        their bytes equivalent.
        """
        self.assertThat(
            generation_hash(unicode(u'abcde')),
            Equals(generation_hash(bytes(b'abcde')))
        )

    def test_consistent_hash(self):
        """
        A given deployment hashes to a specific value.
        """
        # Unfortunately these are manually created golden values generated by
        # running the test with wrong values and copying the output into this
        # file. This test mostly adds value in verifying that the hashes
        # computed in all of our CI environments are the same.
        TEST_DEPLOYMENT_1_HASH = ''.join(chr(x) for x in [
            0x87, 0x13, 0xcb, 0x47, 0x60, 0xd7, 0xab, 0x0f,
            0x30, 0xd5, 0xd2, 0x78, 0xe8, 0x12, 0x5d, 0x11
        ])
        TEST_DEPLOYMENT_2_HASH = ''.join(chr(x) for x in [
            0x5f, 0xc0, 0x2b, 0x4c, 0x57, 0x75, 0x35, 0xff,
            0x6d, 0x1f, 0xd2, 0xc0, 0x14, 0xcf, 0x45, 0x32
        ])
        self.assertThat(
            generation_hash(TEST_DEPLOYMENT_1),
            Equals(TEST_DEPLOYMENT_1_HASH)
        )
        self.assertThat(
            generation_hash(TEST_DEPLOYMENT_2),
            Equals(TEST_DEPLOYMENT_2_HASH)
        )
