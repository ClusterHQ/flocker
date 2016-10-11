from unittest import TestCase

import requests

from ..network import with_network_simulator

HTTPBIN_HOSTNAME = "httpbin.org"

def get(expected_value):
    return requests.get(
        "http://{}/get?expected_value={}".format(HTTPBIN_HOSTNAME, expected_value),
        timeout=2,
    ).json()["args"]["expected_value"]


class NetworkTests(TestCase):
    def test_a(self):
        self.assertEqual("bar", get("bar"))

    @with_network_simulator
    def test_b(self, network):
        network.add_host(HTTPBIN_HOSTNAME)
        network.drop()
        self.assertEqual("bar", get("bar"))

    def test_c(self):
        self.assertEqual("bar", get("bar"))
