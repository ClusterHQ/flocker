# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.node.gear`."""

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.internet.test.connectionmixins import findFreePort

from ...testtools import random_name
from ..gear import IGearClient, FakeGearClient, AlreadyExists, PortMap, GearUnit


def make_igearclient_tests(fixture):
    """
    Create a TestCase for IGearClient.

    :param fixture: A fixture that returns a :class:`IGearClient`
        provider.
    """
    class IGearClientTests(TestCase):
        """
        Tests for :class:`IGearClientTests`.

        These are functional tests if run against a real geard.
        """
        def test_interface(self):
            """The tested object provides :class:`IGearClient`."""
            client = fixture(self)
            self.assertTrue(verifyObject(IGearClient, client))

        def test_add_and_remove(self):
            """An added unit can be removed without an error."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"busybox")
            d.addCallback(lambda _: client.remove(name))
            return d

        def test_no_double_add(self):
            """Adding a unit with name that already exists results in error."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"busybox")

            def added(_):
                self.addCleanup(client.remove, name)
                return client.add(name, u"busybox")
            d.addCallback(added)
            d = self.assertFailure(d, AlreadyExists)
            d.addCallback(lambda exc: self.assertEqual(exc.args[0], name))
            return d

        def test_remove_nonexistent_is_ok(self):
            """Removing a non-existent unit does not result in a error."""
            client = fixture(self)
            name = random_name()
            return client.remove(name)

        def test_double_remove_is_ok(self):
            """Removing a unit twice in a row does not result in error."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"busybox")
            d.addCallback(lambda _: client.remove(name))
            d.addCallback(lambda _: client.remove(name))
            return d

        def test_unknown_does_not_exist(self):
            """A unit that was never added does not exist."""
            client = fixture(self)
            name = random_name()
            d = client.exists(name)
            d.addCallback(self.assertFalse)
            return d

        def test_added_exists(self):
            """An added unit exists."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"busybox")

            def added(_):
                self.addCleanup(client.remove, name)
                return client.exists(name)
            d.addCallback(added)
            d.addCallback(self.assertTrue)
            return d

        def test_removed_does_not_exist(self):
            """A removed unit does not exist."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"busybox")
            d.addCallback(lambda _: client.remove(name))
            d.addCallback(lambda _: client.exists(name))
            d.addCallback(self.assertFalse)
            return d

        def test_add_and_get(self):
            """
            An added unit can be got.
            """
            name = random_name()

            expected_unit = GearUnit(
                unit_name=name,
                image_name=u"openshift/busybox-http-app",
                ports=[PortMap(internal=8080, external=findFreePort()[1])]
            )
            client = fixture(self)
            d = client.add(
                unit_name=expected_unit.unit_name,
                image_name=expected_unit.image_name,
                ports=expected_unit.ports
            )

            def check_unit(actual_unit, expected_unit, testcase):
                testcase.assertEqual(expected_unit, actual_unit)

            def added(unit):
                self.addCleanup(client.remove, name)
                d = client.get(name)
                d.addCallback(check_unit, expected_unit, self)
                return d

            d.addCallback(added)
            return d


    return IGearClientTests


class FakeIGearClientTests(make_igearclient_tests(lambda t: FakeGearClient())):
    """``IGearClient`` tests for ``FakeGearClient``."""


class PortMapTests(TestCase):
    """
    Tests for ``PortMap``.
    """
    def test_init(self):
        """
        ``PortMap`` accepts and `internal` and `external` port integers which
        are exposed as public attributes.
        """
        internal_port = 1234
        external_port = 5678
        port_map = PortMap(internal=internal_port, external=external_port)
        self.assertEqual(
            (internal_port, external_port),
            (port_map.internal, port_map.external)
        )

    def test_repr(self):
        """
        ``PortMap.__repr__`` shows the internal and external ports.
        """
        self.assertEqual(
            "<PortMap(internal=1234, external=5678)>",
            repr(PortMap(internal=1234, external=5678))
        )

    def test_equal(self):
        """
        ``PortMap`` instances with the same internal and external ports compare
        equal.
        """
        self.assertEqual(
            PortMap(internal=1234, external=5678),
            PortMap(internal=1234, external=5678)
        )


    def test_not_equal(self):
        """
        ``PortMap`` instances with the different internal and external ports
        do not compare equal.
        """
        self.assertNotEqual(
            PortMap(internal=5678, external=1234),
            PortMap(internal=1234, external=5678)
        )


class GearUnitTests(TestCase):
    """
    Tests for ``GearUnit``.
    """
    def test_init(self):
        """
        ``GearUnit`` accepts `unit_name`, `image_name` and `ports` arguments
        which are exposed as public attributes.
        """
        unit_name = u'busybox-unit'
        image_name = u'busybox'
        ports = [
            PortMap(internal=1234, external=5678)
        ]
        unit = GearUnit(unit_name=unit_name, image_name=image_name, ports=ports)
        self.assertEqual(
            (unit_name, image_name, ports),
            (unit.unit_name, unit.image_name, unit.ports)
        )

    def test_repr(self):
        """
        ``GearUnit.__repr__`` shows the unit name, image name and ports.
        """
        unit = GearUnit(
            unit_name=u'busybox-unit',
            image_name=u'busybox',
            ports=[PortMap(internal=1234, external=5678)]
        )
        self.assertEqual(
            "<GearUnit("
            "unit_name=u'busybox-unit', "
            "image_name=u'busybox', "
            "ports=[<PortMap(internal=1234, external=5678)>])>",
            repr(unit)
        )

    def test_equal(self):
        """
        ``GearUnit`` instances with the same attributes compare equal.
        """
        u1 = GearUnit(
            unit_name=u'busybox-unit',
            image_name=u'busybox',
            ports=[PortMap(internal=1234, external=5678)]
        )

        u2 = GearUnit(
            unit_name=u'busybox-unit',
            image_name=u'busybox',
            ports=[PortMap(internal=1234, external=5678)]
        )
        self.assertEqual(u1, u2)


    def test_not_equal(self):
        """
        ``PortMap`` instances with the different internal and external ports
        do not compare equal.
        """
        u1 = GearUnit(
            unit_name=u'busybox-unit',
            image_name=u'busybox',
            ports=[PortMap(internal=1234, external=5678)]
        )

        u2 = GearUnit(
            unit_name=u'busybox-variant-unit',
            image_name=u'busybox-variant',
            ports=[PortMap(internal=4321, external=8765)]
        )
        self.assertNotEqual(u1, u2)
