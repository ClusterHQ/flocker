# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.node.gear`."""

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase

from ...testtools import random_name, WithInitTestsMixin
from ..gear import (
    IGearClient, FakeGearClient, AlreadyExists, GearUnit, PortMap, UnknownUnit
)

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

        def test_get_exists(self):
            """A ``GearUnit`` is returned"""
            client = fixture(self)
            name = random_name()
            expected = GearUnit(
                unit_name=name,
                image_name=u'openshift/busybox-http-app',
                ports=[]
            )
            d = client.add(expected.unit_name, expected.image_name, wait_for_start=True)
            d.addCallback(lambda _: client.get(name))
            d.addCallback(self.assertEqual, expected)
            return d

        def test_get_does_not_exist(self):
            """
            ``UnknownUnit`` is raised if a unit with the given name is not
            found.
            """
            client = fixture(self)
            name = random_name()
            get_result = client.get(name)
            def test_error(failure):
                """
                Test the exception type and its value.
                """
                failure.trap(UnknownUnit)
                self.assertEqual(name, failure.value.unit_name)
            get_result.addBoth(test_error)
            return get_result

    return IGearClientTests


class FakeIGearClientTests(make_igearclient_tests(lambda t: FakeGearClient())):
    """``IGearClient`` tests for ``FakeGearClient``."""


class PortMapTests(WithInitTestsMixin, TestCase):
    """
    Tests for ``PortMap``.
    """
    record_type = PortMap
    values = dict(
        internal=1234,
        external=5678,
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


class GearUnitTests(WithInitTestsMixin, TestCase):
    """
    Tests for ``GearUnit``.
    """
    record_type = GearUnit
    values = dict(
        unit_name=u'busybox-unit',
        image_name=u'busybox',
        ports=[
            PortMap(internal=1234, external=5678),
        ]
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


class UnknownUnitTests(WithInitTestsMixin, TestCase):
    """
    Tests for ``UnknownUnit``.
    """
    record_type = UnknownUnit
    values = dict(
        unit_name=u'busybox-app'
    )

    def test_repr(self):
        """
        ``GearUnit.__repr__`` shows the unit name, image name and ports.
        """
        record = UnknownUnit(**self.values)
        self.assertEqual(
            "<UnknownUnit(unit_name=u'busybox-app')>",
            repr(record)
        )
