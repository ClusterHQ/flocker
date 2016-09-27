# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.cinder``.
"""

from ..cinder import _openstack_verify_from_config, _get_compute_id
from ....common import ipaddress_from_string
from ....testtools import TestCase


class VerifyTests(TestCase):
    """
    Tests for _openstack_verify_from_config.
    """

    def test_verify_not_set(self):
        """
        HTTPS connections are verified using system CA's if not
        overridden.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
        }
        self.assertEqual(_openstack_verify_from_config(**config), True)

    def test_verify_ca_path(self):
        """
        HTTPS connections are verified using a CA bundle if
        ``verify_ca_path`` is provided.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
            'verify_peer': True,
            'verify_ca_path': '/a/path'
        }
        self.assertEqual(_openstack_verify_from_config(**config), '/a/path')

    def test_verify_false(self):
        """
        HTTPS connections are not verified if ``verify_peer`` is false.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
            'verify_peer': False,
        }
        self.assertEqual(_openstack_verify_from_config(**config), False)

    def test_verify_false_ca_path(self):
        """
        HTTPS connections are not verified if ``verify_peer`` is false,
        even if a ``verify_ca_path`` is provided.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
            'verify_peer': False,
            'verify_ca_path': '/a/path'
        }
        self.assertEqual(_openstack_verify_from_config(**config), False)


class GetComputeIdTests(TestCase):
    """
    Tests for ``_get_compute_id``.
    """
    def test_local_ips_equal_reported_ips(self):
        """
        If local IPs are the same as a node's IPs that node is the one
        chosen.
        """
        local_ips_1 = {ipaddress_from_string("192.0.0.1"),
                       ipaddress_from_string("10.0.0.1")}
        local_ips_2 = {ipaddress_from_string("10.0.0.2")}
        reported_ips = {u"server1": local_ips_1,
                        u"server2": local_ips_2}
        self.assertEqual(
            (_get_compute_id(local_ips_1, reported_ips),
             _get_compute_id(local_ips_2, reported_ips)),
            (u"server1", u"server2"))

    def test_local_ips_superset_of_reported_ips(self):
        """
        If local IPs are a superset of a node's IPs that node is the one
        chosen.

        We expect local IPs to include addresses like 127.0.0.1 which
        won't show up in reported IPs for remote nodes.
        """
        local_ips_1 = {ipaddress_from_string("192.0.0.1"),
                       ipaddress_from_string("10.0.0.1")}
        local_ips_2 = {ipaddress_from_string("10.0.0.2"),
                       ipaddress_from_string("192.0.0.2")}
        reported_ips = {u"server1": {ipaddress_from_string("192.0.0.1")},
                        u"server2": {ipaddress_from_string("192.0.0.2")}}
        self.assertEqual(
            (_get_compute_id(local_ips_1, reported_ips),
             _get_compute_id(local_ips_2, reported_ips)),
            (u"server1", u"server2"))

    def test_local_ips_subset_of_reported_ips(self):
        """
        If local IPs are a subset of a node's IPs that node is the one chosen.

        Floating IPs will show up in reported IPs for remote nodes but are
        not known to the local machine.
        """
        local_ips_1 = {ipaddress_from_string("192.0.0.1")}
        local_ips_2 = {ipaddress_from_string("192.0.0.2")}
        reported_ips = {u"server1": {ipaddress_from_string("192.0.0.1"),
                                     ipaddress_from_string("10.0.0.1")},
                        u"server2": {ipaddress_from_string("192.0.0.2"),
                                     ipaddress_from_string("10.0.0.2")}}
        self.assertEqual(
            (_get_compute_id(local_ips_1, reported_ips),
             _get_compute_id(local_ips_2, reported_ips)),
            (u"server1", u"server2"))

    def test_local_ips_intersection_of_reported_ips(self):
        """
        If local IPs intersect with a node's IPs that node is the one chosen.

        This can happen if there are floating IPs reported for remote node
        and local list includes things like 127.0.0.1.
        """
        local_ips_1 = {ipaddress_from_string("192.0.0.1"),
                       ipaddress_from_string("127.0.0.1")}
        local_ips_2 = {ipaddress_from_string("192.0.0.2"),
                       ipaddress_from_string("127.0.0.1")}
        reported_ips = {u"server1": {ipaddress_from_string("192.0.0.1"),
                                     ipaddress_from_string("10.0.0.1")},
                        u"server2": {ipaddress_from_string("192.0.0.2"),
                                     ipaddress_from_string("10.0.0.2")}}
        self.assertEqual(
            (_get_compute_id(local_ips_1, reported_ips),
             _get_compute_id(local_ips_2, reported_ips)),
            (u"server1", u"server2"))

    def test_unknown_ip(self):
        """
        A ``KeyError`` is raised if ID can't be calculated.
        """
        local_ips = {ipaddress_from_string("192.0.0.1"),
                     ipaddress_from_string("10.0.0.1")}
        reported_ips = {u"server2": {ipaddress_from_string("192.0.0.2")}}
        self.assertRaises(KeyError, _get_compute_id, local_ips, reported_ips)

    def test_reported_ips_empty(self):
        """
        If reported IPs are blank that node is never chosen.
        """
        local_ips = {ipaddress_from_string("192.0.0.1"),
                     ipaddress_from_string("10.0.0.1")}
        reported_ips = {u"server2": {ipaddress_from_string("192.0.0.1")},
                        u"server1": set()}
        self.assertEqual(_get_compute_id(local_ips, reported_ips), u"server2")
