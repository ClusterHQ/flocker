# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Unit Tests for utilities in ``flocker.node.agents.gce``.
"""

from testtools.matchers import (
    Contains,
    Equals,
    MatchesAll,
    MatchesException,
    MatchesStructure,
    Raises,
)
from zope.interface.verify import verifyClass

from ....testtools import TestCase

from ..gce import (
    GCEOperations,
    GlobalOperationPoller,
    IGCEOperations,
    MalformedOperation,
    OperationPoller,
    ZoneOperationPoller,
    _create_poller,
)


class OperationPollerTests(TestCase):
    """
    Tests for the implementors of :class:`OperationPoller`.
    """

    def test_zone_operation_poller_interface(self):
        """
        ``ZoneOperationPoller`` implements the ``OperationPoller`` interface.
        """
        verifyClass(OperationPoller, ZoneOperationPoller)

    def test_global_operation_poller_interface(self):
        """
        ``GlobalOperationPoller`` implements the ``OperationPoller`` interface.
        """
        verifyClass(OperationPoller, GlobalOperationPoller)


class CreatePollerTests(TestCase):
    """
    Tests for :func:`_create_poller`.
    """

    def test_zone_happy_bytes(self):
        """
        Dicts with ``name`` and well formed ``zone`` as bytes() have
        :class:`ZoneOperationPollers` to poll their status.
        """
        self.assertThat(
            _create_poller(
                {b'name': b'cat', b'zone': b'projects/PP/zones/ZZ'}),
            Equals(ZoneOperationPoller(
                zone=u"ZZ",
                project=u"PP",
                operation_name=u"cat",
            ))
        )

    def test_zone_happy_unicode(self):
        """
        Dicts with ``name`` and well formed ``zone`` as unicode() have
        :class:`ZoneOperationPollers` to poll their status.
        """
        self.assertThat(
            _create_poller(
                {u'name': u'cat', u'zone': u'projects/PP/zones/ZZ'}),
            Equals(ZoneOperationPoller(
                zone=u"ZZ",
                project=u"PP",
                operation_name=u"cat",
            ))
        )

    def test_zone_happy_long(self):
        """
        Dicts with ``name`` and well formed ``zone`` as the long form zone have
        :class:`ZoneOperationPollers` to poll their status.
        """
        self.assertThat(
            _create_poller(
                {u'name': u'cat',
                 u'zone': u'https://content.googleapis.com/compute/v1/'
                          u'projects/PP/zones/ZZ'}),
            Equals(ZoneOperationPoller(
                zone=u"ZZ",
                project=u"PP",
                operation_name=u"cat",
            ))
        )

    def test_global_happy_bytes(self):
        """
        Dicts with ``name`` and ``selfLink`` as bytes and no ``zone`` have
        :class:`GlobalOperationPoller` to poll their status.
        """
        self.assertThat(
            _create_poller({
                b'name': b'cat',
                b'selfLink': b'projects/PP/global/operations/cat'
            }),
            Equals(GlobalOperationPoller(
                project=u"PP",
                operation_name=u"cat",
            ))
        )

    def test_global_happy_unicode(self):
        """
        Dicts with ``name`` and ``selfLink`` as unicode and no ``zone`` have
        :class:`GlobalOperationPoller` to poll their status.
        """
        self.assertThat(
            _create_poller({
                u'name': u'cat',
                u'selfLink': u'projects/PP/global/operations/cat'
            }),
            Equals(GlobalOperationPoller(
                project=u"PP",
                operation_name=u"cat",
            ))
        )

    def test_global_no_selfLink(self):
        """
        Dicts with ``name`` but no ``selfLink`` and no ``zone`` raise an error
        that will help in debugging.
        """
        name = u"RARENAME"
        self.assertThat(
            lambda: _create_poller({
                u'name': name,
            }),
            Raises(
                MatchesException(
                    MalformedOperation,
                    MatchesStructure(
                        message=MatchesAll(
                            Contains('selfLink'),  # The missing key.
                            Contains(name),  # The name of the operation.
                        )
                    )
                )
            )
        )

    def test_global_bad_selfLink(self):
        """
        Dicts with ``name`` and a malformed ``selfLink`` and no ``zone`` raise
        an error that will help in debugging.
        """
        name = u"RARENAME"
        selfLink = u"BADSELF"
        self.assertThat(
            lambda: _create_poller({
                u'name': name,
                u'selfLink': selfLink
            }),
            Raises(
                MatchesException(
                    MalformedOperation,
                    MatchesStructure(
                        message=MatchesAll(
                            Contains(selfLink),  # The actual value.
                            Contains('/global/operations/'),  # Expected url.
                            Contains('selfLink'),  # The malformed key.
                            Contains(name),  # The name of the operation.
                        )
                    )
                )
            )
        )

    def test_global_numerical_selfLink(self):
        """
        Dicts with ``name`` and a numerical ``selfLink`` and no ``zone`` raise
        an error that will help in debugging.
        """
        name = u"RARENAME"
        selfLink = 123
        self.assertThat(
            lambda: _create_poller({
                u'name': name,
                u'selfLink': selfLink
            }),
            Raises(
                MatchesException(
                    MalformedOperation,
                    MatchesStructure(
                        message=MatchesAll(
                            Contains(unicode(selfLink)),  # The actual value.
                            Contains('/global/operations/'),  # Expected url.
                            Contains('selfLink'),  # The malformed key.
                            Contains(name),  # The name of the operation.
                        )
                    )
                )
            )
        )

    def test_no_name(self):
        """
        Dicts with no ``name`` raise an error that helps with debugging.
        """
        selfLink = u"BADSELF"
        self.assertThat(
            lambda: _create_poller({
                u'selfLink': selfLink
            }),
            Raises(
                MatchesException(
                    MalformedOperation,
                    MatchesStructure(
                        message=MatchesAll(
                            Contains('name'),  # Missing key
                            Contains(selfLink),  # part of the operation
                        )
                    )
                )
            )
        )

    def test_zone_malformed_zone(self):
        """
        Dicts with ``name`` and malformed ``zone`` without enough slashes raise
        an error that can assist in debugging.
        """
        name = u'CATACTAC'
        zone = u'BADZONEBAD'
        self.assertThat(
            lambda: _create_poller(
                {u'name': name,
                 u'zone': zone}),
            Raises(
                MatchesException(
                    MalformedOperation,
                    MatchesStructure(
                        message=MatchesAll(
                            Contains(zone),  # Actual zone.
                            Contains('/zones/'),  # Expected format.
                            Contains(name),  # The name of the operation.
                        )
                    )
                )
            )
        )

    def test_zone_nolength_zone(self):
        """
        Dicts with ``name` and empty ``zone` raise an error that can assist in
        debugging.
        """
        name = u'CATACTAC'
        self.assertThat(
            lambda: _create_poller(
                {u'name': name,
                 u'zone': u''}),
            Raises(
                MatchesException(
                    MalformedOperation,
                    MatchesStructure(
                        message=MatchesAll(
                            Contains('/zones/'),  # Expected format.
                            Contains(name),  # The name of the operation.
                        )
                    )
                )
            )
        )


class GCEOperationsTests(TestCase):
    """
    Tests for :class:`GCEOperations`
    """

    def test_interface(self):
        """
        :class:`GCEOperations` implements :class:`IGCEOperations`.
        """
        verifyClass(IGCEOperations, GCEOperations)
