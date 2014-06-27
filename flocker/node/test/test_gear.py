# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.node.gear`."""

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase

from ...testtools import random_name, make_with_init_tests
from ..gear import IGearClient, FakeGearClient, AlreadyExists, PortMap


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

    return IGearClientTests


class FakeIGearClientTests(make_igearclient_tests(lambda t: FakeGearClient())):
    """``IGearClient`` tests for ``FakeGearClient``."""



class PortMapInitTests(
        make_with_init_tests(
            record_type=PortMap,
            kwargs = dict(
                internal=1234,
                external=5678,
            )
        )
):
    """
    Tests for ``PortMap.__init__``.
    """


class PortMapTests(TestCase):
    """
    Tests for ``PortMap``.

    XXX: The equality tests in this case are incomplete. See
    https://github.com/hynek/characteristic/issues/4 for a proposed solution to
    this.
    """
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
