# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Flocker Kubernetes plugin.
"""
import os
import json
from pyrsistent import PClass, field
from twisted.internet import reactor

from ...testtools import AsyncTestCase, async_runner, random_name
from ..testtools import (
    require_cluster, ACCEPTANCE_TEST_TIMEOUT, check_and_decode_json
)

from ...ca._validation import treq_with_ca
from twisted.web.http import (
    CREATED as HTTP_CREATED,
    OK as HTTP_OK
)
from twisted.python.filepath import FilePath
FLOCKER_ROOT = FilePath(__file__).parent().parent().parent().parent()
KUBERNETES_DEPLOYMENT = {
    "apiVersion": "extensions/v1beta1",
    "metadata": {
        "name": "nginx-deployment"
    },
    "kind": "Deployment",
    "spec": {
        "template": {
            "spec": {
                "containers": [
                    {
                        "image": "nginx:1.7.9",
                        "name": "nginx",
                        "ports": [
                            {
                                "containerPort": 80
                            }
                        ]
                    }
                ]
            },
            "metadata": {
                "labels": {
                    "app": "nginx"
                }
            }
        },
        "replicas": 3
    },
}


class KubernetesClient(PClass):
    client = field()
    baseurl = field()
    token = field()

    def namespace_create(self, name):
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": name,
            }
        }
        d = self.client.post(
            self.baseurl + b"/api/v1/namespaces",
            json.dumps(namespace),
            headers={
                b"content-type": b"application/json",
                b"Authorization": b"Bearer {}".format(self.token),
            },
        )
        d.addCallback(check_and_decode_json, HTTP_CREATED)
        return d

    def namespace_delete(self, name):
        d = self.client.delete(
            self.baseurl + b"/api/v1/namespaces/" + name,
            headers={
                b"content-type": b"application/json",
                b"Authorization": b"Bearer {}".format(self.token),
            },
        )
        d.addCallback(check_and_decode_json, HTTP_OK)
        return d


def kubernetes_client(reactor, api_address, api_port, token):
    return KubernetesClient(
        client=treq_with_ca(
            reactor,
            ca_path=FLOCKER_ROOT.descendant([".kube", "config", "ca.pem"]),
            expected_common_name=u"kubernetes",
        ),
        baseurl=b"https://%s:%s" % (api_address, api_port),
        token=token,
    )


def kubernetes_namespace_for_test(test, client):
    # Namespace must be a DNS label and at most 63 characters
    namespace_name = random_name(test)
    namespace_name = namespace_name[-63:]
    namespace_name = "-".join(filter(None, namespace_name.split("_")))
    namespace_name = namespace_name.lower()

    d = client.namespace_create(name=namespace_name)

    def delete_namespace():
        return client.namespace_delete(namespace_name)

    def setup_cleanup(ignored_result):
        test.addCleanup(delete_namespace)

    d.addCallback(setup_cleanup)
    d.addCallback(lambda _: namespace_name)
    return d


class KubernetesPluginTests(AsyncTestCase):
    """
    Tests for the Kubernetes plugin.
    """
    run_tests_with = async_runner(timeout=ACCEPTANCE_TEST_TIMEOUT)

    @require_cluster(1)
    def test_create_pod(self, cluster):
        """
        A pod with a Flocker volume can be created.
        """
        client = kubernetes_client(
            reactor,
            api_address=cluster.control_node.public_address,
            api_port=6443,
            token=os.environ["FLOCKER_ACCEPTANCE_KUBERNETES_TOKEN"]
        )

        d = kubernetes_namespace_for_test(self, client)

        return d
