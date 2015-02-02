# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for linking containers.
"""
from socket import error
from telnetlib import Telnet
from unittest import SkipTest, skipUnless
from uuid import uuid4

from pyrsistent import pmap

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.exceptions import TransportError
    ELASTICSEARCH_INSTALLED = True
except ImportError:
    ELASTICSEARCH_INSTALLED = False

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    SELENIUM_INSTALLED = True
except ImportError:
    SELENIUM_INSTALLED = False

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.control import (
    Application, DockerImage, AttachedVolume, Port, Dataset,
    Manifestation)
from flocker.testtools import loop_until

from .testtools import (assert_expected_deployment, flocker_deploy, get_nodes,
                        require_flocker_cli)

ELASTICSEARCH_INTERNAL_PORT = 9200
ELASTICSEARCH_EXTERNAL_PORT = 9200

ELASTICSEARCH_APPLICATION_NAME = u"elasticsearch"
ELASTICSEARCH_IMAGE = u"clusterhq/elasticsearch"
ELASTICSEARCH_VOLUME_MOUNTPOINT = u'/var/lib/elasticsearch'

ELASTICSEARCH_APPLICATION = Application(
    name=ELASTICSEARCH_APPLICATION_NAME,
    image=DockerImage.from_string(ELASTICSEARCH_IMAGE),
    ports=frozenset([
        Port(internal_port=ELASTICSEARCH_INTERNAL_PORT,
             external_port=ELASTICSEARCH_EXTERNAL_PORT),
    ]),
    volume=AttachedVolume(
        manifestation=Manifestation(
            dataset=Dataset(
                dataset_id=unicode(uuid4()),
                metadata=pmap({"name": ELASTICSEARCH_APPLICATION_NAME})),
            primary=True),
        mountpoint=FilePath(ELASTICSEARCH_VOLUME_MOUNTPOINT),
    ),
)

LOGSTASH_INTERNAL_PORT = 5000
LOGSTASH_EXTERNAL_PORT = 5000

LOGSTASH_LOCAL_PORT = 9200
LOGSTASH_REMOTE_PORT = 9200

LOGSTASH_APPLICATION_NAME = u"logstash"
LOGSTASH_IMAGE = u"clusterhq/logstash"

LOGSTASH_APPLICATION = Application(
    name=LOGSTASH_APPLICATION_NAME,
    image=DockerImage.from_string(LOGSTASH_IMAGE),
    ports=frozenset([
        Port(internal_port=LOGSTASH_INTERNAL_PORT,
             external_port=LOGSTASH_INTERNAL_PORT),
    ]),
)

KIBANA_INTERNAL_PORT = 8080
KIBANA_EXTERNAL_PORT = 80

KIBANA_APPLICATION_NAME = u"kibana"
KIBANA_IMAGE = u"clusterhq/kibana"

KIBANA_APPLICATION = Application(
    name=KIBANA_APPLICATION_NAME,
    image=DockerImage.from_string(KIBANA_IMAGE),
    ports=frozenset([
        Port(internal_port=KIBANA_INTERNAL_PORT,
             external_port=KIBANA_EXTERNAL_PORT),
    ]),
)

MESSAGES = set([
    str({"firstname": "Joe", "lastname": "Bloggs"}),
    str({"firstname": "Fred", "lastname": "Bloggs"}),
])

require_elasticsearch = skipUnless(
    ELASTICSEARCH_INSTALLED, "elasticsearch not installed")

require_selenium = skipUnless(
    SELENIUM_INSTALLED, "Selenium not installed")


class LinkingTests(TestCase):
    """
    Tests for linking containers with Flocker. In particular, tests for linking
    Logstash and Elasticsearch containers and what happens when the
    Elasticsearch container is moved.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/examples/linking.html
    """
    @require_flocker_cli
    def setUp(self):
        """
        Deploy Elasticsearch, logstash and Kibana to one of two nodes.
        """
        getting_nodes = get_nodes(self, num_nodes=2)

        def deploy_elk(node_ips):
            self.node_1, self.node_2 = node_ips

            elk_deployment = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [
                        ELASTICSEARCH_APPLICATION_NAME,
                        LOGSTASH_APPLICATION_NAME,
                        KIBANA_APPLICATION_NAME,
                    ],
                    self.node_2: [],
                },
            }

            self.elk_deployment_moved = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [LOGSTASH_APPLICATION_NAME,
                                  KIBANA_APPLICATION_NAME],
                    self.node_2: [ELASTICSEARCH_APPLICATION_NAME],
                },
            }

            es_dataset_id = ELASTICSEARCH_APPLICATION.volume.dataset.dataset_id
            self.elk_application = {
                u"version": 1,
                u"applications": {
                    ELASTICSEARCH_APPLICATION_NAME: {
                        u"image": ELASTICSEARCH_IMAGE,
                        u"ports": [{
                            u"internal": ELASTICSEARCH_INTERNAL_PORT,
                            u"external": ELASTICSEARCH_EXTERNAL_PORT,
                        }],
                        u"volume": {
                            u"dataset_id": es_dataset_id,
                            u"mountpoint": ELASTICSEARCH_VOLUME_MOUNTPOINT,
                        },
                    },
                    LOGSTASH_APPLICATION_NAME: {
                        u"image": LOGSTASH_IMAGE,
                        u"ports": [{
                            u"internal": LOGSTASH_INTERNAL_PORT,
                            u"external": LOGSTASH_EXTERNAL_PORT,
                        }],
                        u"links": [{
                            u"local_port": LOGSTASH_LOCAL_PORT,
                            u"remote_port": LOGSTASH_REMOTE_PORT,
                            u"alias": u"es",
                        }],
                    },
                    KIBANA_APPLICATION_NAME: {
                        u"image": KIBANA_IMAGE,
                        u"ports": [{
                            u"internal": KIBANA_INTERNAL_PORT,
                            u"external": KIBANA_EXTERNAL_PORT,
                        }],
                    },
                },
            }

            flocker_deploy(self, elk_deployment, self.elk_application)

        return getting_nodes.addCallback(deploy_elk)

    def test_deploy(self):
        """
        The test setUp deploys Elasticsearch, logstash and Kibana to the same
        node.
        """
        return assert_expected_deployment(self, {
            self.node_1: set([ELASTICSEARCH_APPLICATION, LOGSTASH_APPLICATION,
                              KIBANA_APPLICATION]),
            self.node_2: set([]),
        })

    @require_selenium
    def test_kibana_connects_es(self):
        """
        Kibana can connect to Elasticsearch.
        """
        try:
            driver = webdriver.PhantomJS()
            self.addCleanup(driver.quit)
        except WebDriverException:
            raise SkipTest("PhantomJS must be installed.")

        url = "http://{ip}:{port}".format(
            ip=self.node_1,
            port=KIBANA_EXTERNAL_PORT)
        no_connect_error = "Could not contact Elasticsearch"
        success = "No results"

        waiting_for_es = self._get_elasticsearch(self.node_1)

        def wait_for_banner():
            """
            After a short amount of time, a banner will be displayed either
            saying that there are no results, or that Kibana cannot connect
            to Elasticsearch. This test can succeed or fail when this
            banner is shown.
            """
            source = driver.page_source
            if no_connect_error in source:
                self.fail("Kibana cannot connect to Elasticsearch.")
            elif success in source:
                return True

        waiting_for_es.addCallback(lambda _: driver.get(url))
        return waiting_for_es.addCallback(
            lambda _: loop_until(wait_for_banner))

    @require_elasticsearch
    def test_elasticsearch_empty(self):
        """
        By default there are no log messages in Elasticsearch.
        """
        return self._assert_expected_log_messages(
            ignored=None,
            node=self.node_1,
            expected_messages=set([]),
        )

    def test_moving_just_elasticsearch(self):
        """
        It is possible to move just Elasticsearch to a new node, keeping
        logstash and Kibana in place.
        """
        flocker_deploy(self, self.elk_deployment_moved, self.elk_application)

        return assert_expected_deployment(self, {
            self.node_1: set([LOGSTASH_APPLICATION, KIBANA_APPLICATION]),
            self.node_2: set([ELASTICSEARCH_APPLICATION]),
        })

    @require_elasticsearch
    def test_logstash_messages_in_elasticsearch(self):
        """
        After sending messages to logstash, those messages can be found by
        searching Elasticsearch.
        """
        sending_messages = self._send_messages_to_logstash(
            node=self.node_1,
            messages=MESSAGES,
        )

        return sending_messages.addCallback(
            self._assert_expected_log_messages,
            node=self.node_1,
            expected_messages=MESSAGES,
        )

    @require_elasticsearch
    def test_moving_data(self):
        """
        After sending messages to logstash and then moving Elasticsearch to
        another node, those messages can still be found in Elasticsearch.
        """
        sending_messages = self._send_messages_to_logstash(
            node=self.node_1,
            messages=MESSAGES,
        )

        checking_messages = sending_messages.addCallback(
            self._assert_expected_log_messages,
            node=self.node_1,
            expected_messages=MESSAGES,
        )

        checking_messages.addCallback(
            lambda _: flocker_deploy(self, self.elk_deployment_moved,
                                     self.elk_application),
        )

        return checking_messages.addCallback(
            self._assert_expected_log_messages,
            node=self.node_2,
            expected_messages=MESSAGES,
        )

    def _get_elasticsearch(self, node):
        """
        Get an Elasticsearch instance on a node once one is available.

        :param node: The node hosting, or soon-to-be hosting, an Elasticsearch
            instance.
        :return: A running ``Elasticsearch`` instance.
        """
        elasticsearch = Elasticsearch(
            hosts=[{"host": node, "port": ELASTICSEARCH_EXTERNAL_PORT}],
        )

        def wait_for_ping():
            if elasticsearch.ping():
                return elasticsearch
            else:
                return False

        waiting_for_ping = loop_until(wait_for_ping)
        return waiting_for_ping

    def _assert_expected_log_messages(self, ignored, node, expected_messages):
        """
        Check that expected messages can eventually be found by Elasticsearch.

        After sending two messages to logstash, checking elasticsearch will
        at first show that there are zero messages, then later one, then later
        two. Therefore this waits for the expected number of search results
        before making an assertion that the search results have the expected
        contents. This means that if the message never arrives, tests calling
        this method may fail due to a timeout error instead of something more
        clear.

        :param node: The node hosting, or soon-to-be hosting, an Elasticsearch
            instance.
        :param set expected_messages: A set of strings expected to be found as
            messages on Elasticsearch.
        """
        getting_elasticsearch = self._get_elasticsearch(node=node)

        def wait_for_hits(elasticsearch):
            def get_hits():
                try:
                    num_hits = elasticsearch.search()[u'hits'][u'total']
                except TransportError:
                    return False

                if num_hits == len(expected_messages):
                    return elasticsearch

            waiting_for_hits = loop_until(get_hits)
            return waiting_for_hits

        waiting_for_messages = getting_elasticsearch.addCallback(wait_for_hits)

        def check_messages(elasticsearch):
            hits = elasticsearch.search()[u'hits'][u'hits']
            messages = set([hit[u'_source'][u'message'] for hit in hits])
            self.assertEqual(messages, expected_messages)

        return waiting_for_messages.addCallback(check_messages)

    def _send_messages_to_logstash(self, node, messages):
        """
        Wait for logstash to start up and then send messages to it using
        Telnet.

        :param node: The node hosting, or soon-to-be hosting, a logstash
            instance.
        :param set expected_messages: A set of strings to send to logstash.
        """
        def get_telnet_connection_to_logstash():
            try:
                return Telnet(host=node, port=LOGSTASH_EXTERNAL_PORT)
            except error:
                return False

        waiting_for_logstash = loop_until(get_telnet_connection_to_logstash)

        def send_messages(telnet):
            for message in messages:
                telnet.write(message + "\n")

        return waiting_for_logstash.addCallback(send_messages)
