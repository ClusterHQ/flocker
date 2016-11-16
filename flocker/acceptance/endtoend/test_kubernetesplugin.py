# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Flocker Kubernetes plugin.
"""
import os
import json
import yaml
from pyrsistent import PClass, field
from twisted.internet import reactor
from eliot import start_action, Message
from eliot.twisted import DeferredContext
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

# Cached output of:
# curl ...  https://kubernetes:6443/apis/extensions/v1beta1
KUBERNETES_API_GROUPS = json.loads("""
{"api": {
  "kind": "APIResourceList",
  "groupVersion": "v1",
  "resources": [
    {
      "name": "bindings",
      "namespaced": true,
      "kind": "Binding"
    },
    {
      "name": "componentstatuses",
      "namespaced": false,
      "kind": "ComponentStatus"
    },
    {
      "name": "configmaps",
      "namespaced": true,
      "kind": "ConfigMap"
    },
    {
      "name": "endpoints",
      "namespaced": true,
      "kind": "Endpoints"
    },
    {
      "name": "events",
      "namespaced": true,
      "kind": "Event"
    },
    {
      "name": "limitranges",
      "namespaced": true,
      "kind": "LimitRange"
    },
    {
      "name": "namespaces",
      "namespaced": false,
      "kind": "Namespace"
    },
    {
      "name": "namespaces/finalize",
      "namespaced": false,
      "kind": "Namespace"
    },
    {
      "name": "namespaces/status",
      "namespaced": false,
      "kind": "Namespace"
    },
    {
      "name": "nodes",
      "namespaced": false,
      "kind": "Node"
    },
    {
      "name": "nodes/proxy",
      "namespaced": false,
      "kind": "Node"
    },
    {
      "name": "nodes/status",
      "namespaced": false,
      "kind": "Node"
    },
    {
      "name": "persistentvolumeclaims",
      "namespaced": true,
      "kind": "PersistentVolumeClaim"
    },
    {
      "name": "persistentvolumeclaims/status",
      "namespaced": true,
      "kind": "PersistentVolumeClaim"
    },
    {
      "name": "persistentvolumes",
      "namespaced": false,
      "kind": "PersistentVolume"
    },
    {
      "name": "persistentvolumes/status",
      "namespaced": false,
      "kind": "PersistentVolume"
    },
    {
      "name": "pods",
      "namespaced": true,
      "kind": "Pod"
    },
    {
      "name": "pods/attach",
      "namespaced": true,
      "kind": "Pod"
    },
    {
      "name": "pods/binding",
      "namespaced": true,
      "kind": "Binding"
    },
    {
      "name": "pods/eviction",
      "namespaced": true,
      "kind": "Eviction"
    },
    {
      "name": "pods/exec",
      "namespaced": true,
      "kind": "Pod"
    },
    {
      "name": "pods/log",
      "namespaced": true,
      "kind": "Pod"
    },
    {
      "name": "pods/portforward",
      "namespaced": true,
      "kind": "Pod"
    },
    {
      "name": "pods/proxy",
      "namespaced": true,
      "kind": "Pod"
    },
    {
      "name": "pods/status",
      "namespaced": true,
      "kind": "Pod"
    },
    {
      "name": "podtemplates",
      "namespaced": true,
      "kind": "PodTemplate"
    },
    {
      "name": "replicationcontrollers",
      "namespaced": true,
      "kind": "ReplicationController"
    },
    {
      "name": "replicationcontrollers/scale",
      "namespaced": true,
      "kind": "Scale"
    },
    {
      "name": "replicationcontrollers/status",
      "namespaced": true,
      "kind": "ReplicationController"
    },
    {
      "name": "resourcequotas",
      "namespaced": true,
      "kind": "ResourceQuota"
    },
    {
      "name": "resourcequotas/status",
      "namespaced": true,
      "kind": "ResourceQuota"
    },
    {
      "name": "secrets",
      "namespaced": true,
      "kind": "Secret"
    },
    {
      "name": "serviceaccounts",
      "namespaced": true,
      "kind": "ServiceAccount"
    },
    {
      "name": "services",
      "namespaced": true,
      "kind": "Service"
    },
    {
      "name": "services/proxy",
      "namespaced": true,
      "kind": "Service"
    },
    {
      "name": "services/status",
      "namespaced": true,
      "kind": "Service"
    }
  ]
},
"apis": {
  "kind": "APIResourceList",
  "groupVersion": "extensions/v1beta1",
  "resources": [
    {
      "name": "daemonsets",
      "namespaced": true,
      "kind": "DaemonSet"
    },
    {
      "name": "daemonsets/status",
      "namespaced": true,
      "kind": "DaemonSet"
    },
    {
      "name": "deployments",
      "namespaced": true,
      "kind": "Deployment"
    },
    {
      "name": "deployments/rollback",
      "namespaced": true,
      "kind": "DeploymentRollback"
    },
    {
      "name": "deployments/scale",
      "namespaced": true,
      "kind": "Scale"
    },
    {
      "name": "deployments/status",
      "namespaced": true,
      "kind": "Deployment"
    },
    {
      "name": "horizontalpodautoscalers",
      "namespaced": true,
      "kind": "HorizontalPodAutoscaler"
    },
    {
      "name": "horizontalpodautoscalers/status",
      "namespaced": true,
      "kind": "HorizontalPodAutoscaler"
    },
    {
      "name": "ingresses",
      "namespaced": true,
      "kind": "Ingress"
    },
    {
      "name": "ingresses/status",
      "namespaced": true,
      "kind": "Ingress"
    },
    {
      "name": "jobs",
      "namespaced": true,
      "kind": "Job"
    },
    {
      "name": "jobs/status",
      "namespaced": true,
      "kind": "Job"
    },
    {
      "name": "networkpolicies",
      "namespaced": true,
      "kind": "NetworkPolicy"
    },
    {
      "name": "replicasets",
      "namespaced": true,
      "kind": "ReplicaSet"
    },
    {
      "name": "replicasets/scale",
      "namespaced": true,
      "kind": "Scale"
    },
    {
      "name": "replicasets/status",
      "namespaced": true,
      "kind": "ReplicaSet"
    },
    {
      "name": "replicationcontrollers",
      "namespaced": true,
      "kind": "ReplicationControllerDummy"
    },
    {
      "name": "replicationcontrollers/scale",
      "namespaced": true,
      "kind": "Scale"
    },
    {
      "name": "thirdpartyresources",
      "namespaced": false,
      "kind": "ThirdPartyResource"
    }
  ]
}}
""")

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
        "replicas": 1
    },
}

FLOCKER_POD = yaml.safe_load("""\
apiVersion: v1
kind: Pod
metadata:
  name: flocker-web
spec:
  containers:
    - name: web
      image: nginx
      ports:
        - name: web
          containerPort: 80
      volumeMounts:
          # name must match the volume name below
          - name: www-root
            mountPath: "/usr/share/nginx/html"
  volumes:
    - name: www-root
      flocker:
          datasetName: my-flocker-vol
""")


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

    def _endpoint_url_for_resource(self, namespace, resource):
        resource_group_version = resource["apiVersion"]
        resource_kind = resource["kind"]

        # Lookup resource list
        for first_url_segment, group_info in KUBERNETES_API_GROUPS.items():
            if group_info["groupVersion"] == resource_group_version:
                break
        else:
            raise Exception(
                "resource_group_version not recognized",
                resource_group_version
            )
        # Lookup the "kind"
        for resource_meta in group_info["resources"]:
            if resource_meta["kind"] == resource_kind:
                break
        else:
            raise Exception(
                "resource_kind not recognized",
                resource_kind
            )

        return "/".join([
            self.baseurl,
            first_url_segment,
            resource_group_version,
            "namespaces",
            namespace,
            resource_meta["name"]
        ])

    def create_resource(self, namespace, resource):
        url = self._endpoint_url_for_resource(namespace, resource)
        action = start_action(
            action_type=u"create_resource",
            namespace=namespace,
            resource=resource,
            url=url,
        )

        with action.context():
            d = self.client.post(
                url,
                json.dumps(resource),
                headers={
                    b"content-type": b"application/json",
                    b"Authorization": b"Bearer {}".format(self.token),
                },
            )
            d = DeferredContext(d)
            d.addCallback(check_and_decode_json, HTTP_CREATED)
            d.addActionFinish()
            return d.result


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
    """
    Create a unique Kubernetes namespace in which to create Kubernetes test
    resources. The namespace will be deleted when the test completes. And
    Kubernetes *should* then garbage collect all the resources in that
    namespace.
    XXX: Although it doesn't always seem to work:
    https://github.com/kubernetes/kubernetes/issues/36891
    """
    # Namespace must be a DNS label and at most 63 characters
    namespace_name = random_name(test)
    namespace_name = namespace_name[-63:]
    namespace_name = "-".join(filter(None, namespace_name.split("_")))
    namespace_name = namespace_name.lower()

    d = client.namespace_create(name=namespace_name)

    def delete_namespace():
        return client.namespace_delete(namespace_name)

    def setup_cleanup(ignored_result):
        return
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

        def create_deployment(namespace):
            return client.create_resource(namespace, FLOCKER_POD)
        d.addCallback(create_deployment)
        return d
