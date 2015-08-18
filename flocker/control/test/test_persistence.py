# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.control._persistence``.
"""
import json

from uuid import uuid4, UUID

from eliot.testing import validate_logging, assertHasMessage, assertHasAction

from twisted.internet import reactor
from twisted.trial.unittest import TestCase, SynchronousTestCase
from twisted.python.filepath import FilePath

from pyrsistent import PRecord

from .._persistence import (
    ConfigurationPersistenceService, wire_decode, wire_encode,
    _LOG_SAVE, _LOG_STARTUP, LeaseService, migrate_configuration,
    _CONFIG_VERSION, ConfigurationMigration, ConfigurationMigrationError,
    _LOG_UPGRADE, MissingMigrationError,
    )
from .._model import (
    Deployment, Application, DockerImage, Node, Dataset, Manifestation,
    AttachedVolume, SERIALIZABLE_CLASSES, NodeState, Configuration,
    )


DATASET = Dataset(dataset_id=u'4e7e3241-0ec3-4df6-9e7c-3f7e75e08855',
                  metadata={u"name": u"myapp"})
MANIFESTATION = Manifestation(dataset=DATASET, primary=True)
TEST_DEPLOYMENT = Deployment(
    nodes=[Node(uuid=UUID(u'ab294ce4-a6c3-40cb-a0a2-484a1f09521c'),
                applications=[
                    Application(
                        name=u'myapp',
                        image=DockerImage.from_string(u'postgresql:7.6'),
                        volume=AttachedVolume(
                            manifestation=MANIFESTATION,
                            mountpoint=FilePath(b"/xxx/yyy"))
                    )],
                manifestations={DATASET.dataset_id: MANIFESTATION})])


V1_TEST_DEPLOYMENT_JSON = FilePath(__file__).sibling(
    'configurations').child(b"configuration_v1.json").getContent()


class FakePersistenceService(object):
    """
    A very simple fake persistence service that does nothing.
    """
    def __init__(self):
        self._deployment = Deployment(nodes=frozenset())

    def save(self, deployment):
        self._deployment = deployment

    def get(self):
        return self._deployment


class LeaseServiceTests(TestCase):
    """
    Tests for ``LeaseService``.
    """
    def service(self):
        """
        Start a lease service and schedule it to stop.

        :return: Started ``LeaseService``.
        """
        service = LeaseService(reactor, FakePersistenceService())
        service.startService()
        self.addCleanup(service.stopService)
        return service

    def test_expired_lease_removed(self):
        """
        A lease that has expired is removed from the persisted
        configuration.

        XXX Leases cannot be manipulated in this branch. See FLOC-2375.
        This is a skeletal test that merely ensures the call to
        ``update_leases`` takes place when ``_expire`` is called and should
        be rewritten to test the updated configuration once the configuration
        is aware of Leases.
        """
        service = self.service()
        d = service._expire()

        def check_expired(updated):
            self.assertIsNone(updated)

        d.addCallback(check_expired)
        return d


class ConfigurationPersistenceServiceTests(TestCase):
    """
    Tests for ``ConfigurationPersistenceService``.
    """
    def service(self, path, logger=None):
        """
        Start a service, schedule its stop.

        :param FilePath path: Where to store data.
        :param logger: Optional eliot ``Logger`` to set before startup.

        :return: Started ``ConfigurationPersistenceService``.
        """
        service = ConfigurationPersistenceService(reactor, path)
        if logger is not None:
            self.patch(service, "logger", logger)
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

    @validate_logging(assertHasAction, _LOG_UPGRADE, succeeded=True,
                      startFields=dict(configuration=V1_TEST_DEPLOYMENT_JSON,
                                       source_version=1, target_version=2))
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
        self.service(path, logger)
        self.assertTrue(path.child(b"current_configuration.json").exists())

    def test_old_configuration_is_upgraded(self):
        """
        The persistence service will detect if an existing configuration
        saved in a file is a previous version and perform a migration to
        the latest version.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        v1_config_file = path.child(b"current_configuration.v1.json")
        v1_config_file.setContent(V1_TEST_DEPLOYMENT_JSON)
        config_path = path.child(b"current_configuration.json")
        self.service(path)
        configuration = wire_decode(config_path.getContent())
        self.assertEqual(configuration.version, _CONFIG_VERSION)

    def test_current_configuration_unchanged(self):
        """
        A persisted configuration saved in the latest configuration
        version is not upgraded and therefore remains unchanged on
        service startup.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        config_path = path.child(b"current_configuration.json")
        config_path.setContent(wire_encode(TEST_DEPLOYMENT))
        self.service(path)
        configuration = wire_decode(config_path.getContent())
        configured_deployment = configuration.deployment
        self.assertEqual(configured_deployment, TEST_DEPLOYMENT)

    @validate_logging(assertHasAction, _LOG_SAVE, succeeded=True,
                      startFields=dict(configuration=TEST_DEPLOYMENT))
    def test_save_then_get(self, logger):
        """
        A configuration that was saved can subsequently retrieved.
        """
        service = self.service(FilePath(self.mktemp()), logger)
        d = service.save(TEST_DEPLOYMENT)
        d.addCallback(lambda _: service.get())
        d.addCallback(self.assertEqual, TEST_DEPLOYMENT)
        return d

    @validate_logging(assertHasMessage, _LOG_STARTUP,
                      fields=dict(configuration=TEST_DEPLOYMENT))
    def test_persist_across_restarts(self, logger):
        """
        A configuration that was saved can be loaded from a new service.
        """
        path = FilePath(self.mktemp())
        service = ConfigurationPersistenceService(reactor, path)
        service.startService()
        d = service.save(TEST_DEPLOYMENT)
        d.addCallback(lambda _: service.stopService())

        def retrieve_in_new_service(_):
            new_service = self.service(path, logger)
            self.assertEqual(new_service.get(), TEST_DEPLOYMENT)
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
        d = service.save(TEST_DEPLOYMENT)

        def saved(_):
            service.register(lambda: callbacks2.append(1))
            return service.save(TEST_DEPLOYMENT)
        d.addCallback(saved)

        def saved_again(_):
            self.assertEqual((callbacks, callbacks2), ([1, 1], [1]))
        d.addCallback(saved_again)
        return d

    @validate_logging(
        lambda test, logger:
        test.assertEqual(len(logger.flush_tracebacks(ZeroDivisionError)), 1))
    def test_register_for_callback_failure(self, logger):
        """
        Failed callbacks don't prevent later callbacks from being called.
        """
        service = self.service(FilePath(self.mktemp()), logger)
        callbacks = []
        service.register(lambda: 1/0)
        service.register(lambda: callbacks.append(1))
        d = service.save(TEST_DEPLOYMENT)

        def saved(_):
            self.assertEqual(callbacks, [1])
        d.addCallback(saved)
        return d


class WireEncodeDecodeTests(SynchronousTestCase):
    """
    Tests for ``wire_encode`` and ``wire_decode``.
    """
    def test_encode_to_bytes(self):
        """
        ``wire_encode`` converts the given object to ``bytes``.
        """
        self.assertIsInstance(wire_encode(TEST_DEPLOYMENT), bytes)

    def test_roundtrip(self):
        """
        ``wire_decode`` returns object passed to ``wire_encode``.
        """
        self.assertEqual(TEST_DEPLOYMENT,
                         wire_decode(wire_encode(TEST_DEPLOYMENT)))

    def test_no_arbitrary_decoding(self):
        """
        ``wire_decode`` will not decode classes that are not in
        ``SERIALIZABLE_CLASSES``.
        """
        class Temp(PRecord):
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


class FakeMigration(object):
    """
    A simple fake migration class, used to test ``migrate_configuration``.
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


class MigrateConfigurationTests(SynchronousTestCase):
    """
    Tests for ``migrate_configuration``.
    """
    v1_config = json.dumps({"version": 1})

    def test_error_on_undefined_migration_path(self):
        """
        A ``ConfigurationMigrationError`` is raised if a migration path
        from one version to another cannot be found in the supplied
        migration class.
        """
        e = self.assertRaises(
            MissingMigrationError,
            migrate_configuration, 1, 4, self.v1_config, FakeMigration
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
        v2_config = migrate_configuration(1, 2, self.v1_config, FakeMigration)
        # Perform two sequential migrations to get from v1 to v3, starting
        # with a v1 config.
        result = migrate_configuration(1, 3, self.v1_config, FakeMigration)
        # Compare the v1 --> v3 upgrade to the direct result of the
        # v2 --> v3 upgrade on the v2 config, Both should be identical
        # and valid v3 configs.
        self.assertEqual(result, FakeMigration.upgrade_from_v2(v2_config))

    def test_v1_latest_configuration(self):
        """
        A V1 JSON configuration blob is transformed to the latest
        configuration, with the result validating when loaded.
        """
        upgraded_json = migrate_configuration(
            1, _CONFIG_VERSION, V1_TEST_DEPLOYMENT_JSON,
            ConfigurationMigration)
        upgraded_config = wire_decode(upgraded_json)
        expected_configuration = Configuration(
            version=_CONFIG_VERSION, deployment=TEST_DEPLOYMENT
        )
        self.assertEqual(upgraded_config, expected_configuration)

    def test_v1_v2_configuration(self):
        """
        A V1 JSON configuration blob can be upgraded to version 2.
        See flocker/control/test/configurations for individual
        version JSON files and generation code.
        """
        upgraded_json = migrate_configuration(
            1, 2, V1_TEST_DEPLOYMENT_JSON, ConfigurationMigration)
        expected_upgraded_json = FilePath(__file__).sibling(
            'configurations').child(b"configuration_v2.json").getContent()
        self.assertEqual(upgraded_json, expected_upgraded_json)


class ConfigurationMigrationTests(SynchronousTestCase):
    """
    Tests for ``ConfigurationMigration`` class that performs individual
    configuration upgrades.
    """
