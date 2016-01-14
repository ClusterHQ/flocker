
import string
import yaml
import os
import sys
from copy import deepcopy
from json import dumps
from itertools import repeat

from treq import json_content

from twisted.internet.defer import inlineCallbacks
from twisted.python.filepath import FilePath
from twisted.python import usage
from twisted.web.http import OK

from flocker.common import loop_until
from flocker.control.httpapi import REST_API_PORT
from flocker.apiclient import FlockerClient
from flocker.ca import treq_with_authentication


class ContainerOptions(usage.Options):
    """
    Parses the options pased as an argument to the create container script.
    """
    # XXX mandatory options
    # XXX validations
    description = "Set up containers in a Flocker cluster."

    optParameters = [
        ['apps-per-node', None, 0, 'Number of application containers per node',
         int],
        ['app-template', None, None,
         'Configuration to use for each application container'],
        ['control-node', None, None,
         'Public IP address of the control node'],
        ['certificate-path', None, None,
         'Location of the user and control certificates and user key'],
        ['purpose', None, 'testing',
         "Purpose of the cluster recorded in its metadata where possible"],
        ['cluster', None, None,
         'Configuration of the cluster'],
    ]

    synopsis = ('Usage: setup-cluster-containers --app-per-node <containers'
                'per node> --app-template <name of the file> '
                '--control-node <IPAddress>'
                '--certificate-path <path where all the certificates are>'
                '[--purpose <string> (UNUSED)]'
                '[--cluster <file> (UNUSED)')

    def postOptions(self):
        if self['app-template'] is not None:
            template_file = FilePath(self['app-template'])
            self['template'] = yaml.safe_load(template_file.getContent())
        elif self['apps-per-node'] > 0:
            raise usage.UsageError(
                "app-template parameter must be provided if apps-per-node > 0"
            )

        self['purpose'] = unicode(self['purpose'])
        if any(x not in string.ascii_letters + string.digits + '-'
               for x in self['purpose']):
            raise usage.UsageError(
                "Purpose may have only alphanumeric symbols and dash. " +
                "Found {!r}".format('purpose')
            )


class ResponseError(Exception):
    """
    An unexpected response from the REST API.
    """
    def __init__(self, code, message):
        Exception.__init__(self, "Unexpected response code {}:\n{}\n".format(
            code, message))
        self.code = code


class ClusterContainerDeployment(object):
    """
    Class that contains all the methods needed to deploy a new config in a
    cluster.

    :ivar options:
    :ivar application_template:
    :ivar per_node:
    :ivar control_node_address:
    :ivar cluster_cert:
    :ivar user_cert:
    :ivar user_key:
    :ivar client:
    :ivar reactor:
    :ivar nodes:
    """
    def __init__(self, reactor, env, options):
        # XXX add the capability to use env variables if the options are not
        # passed
        # self.control_node_address = env['FLOCKER_ACCEPTANCE_CONTROL_NODE']
        # self.certificates_path = FilePath(
        #    env['FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH'])
        self.options = options
        try:
            self.application_template = self.options['template']
            self.per_node = self.options['apps-per-node']
            self.control_node_address = self.options['control-node']
        except Exception as e:
            sys.stderr.write("%s: %s\n" % ("Missing or wrong arguments", e))
            raise SystemExit(1)

        certificates_path = FilePath(self.options['certificate-path'])
        self.cluster_cert = certificates_path.child(b"cluster.crt")
        self.user_cert = certificates_path.child(b"user.crt")
        self.user_key = certificates_path.child(b"user.key")
        self.client = None
        self.reactor = reactor
        self.nodes = []
        self._initialise_client()

    def _initialise_client(self):
        self.client = FlockerClient(
            self.reactor,
            self.control_node_address,
            REST_API_PORT,
            self.cluster_cert,
            self.user_cert,
            self.user_key
        )

    def _set_nodes(self, nodes):
        self.nodes = nodes

    def deploy(self):
        d = self.client.list_nodes()
        d.addCallback(self._set_nodes)
        d.addCallback(self._build_config)
        d.addCallback(self._configure)
        return d

    def is_datasets_deployment_complete(self):
        number_of_datasets = self.per_node * len(self.nodes)

        d = self.client.list_datasets_state()

        def do_we_have_enough_datasets(datasets):
            return (len(datasets) >= number_of_datasets)

        d.addCallback(do_we_have_enough_datasets)
        return d

    def is_container_deployment_complete(self):
        number_of_containers = self.per_node * len(self.nodes)

        d = self.client.list_containers_state()

        def do_we_have_enough_containers(containers):
            return (len(containers) >= number_of_containers)

        d.addCallback(do_we_have_enough_containers)
        return d

    @inlineCallbacks
    def deploy_and_wait_for_creation(self):
        yield self.deploy()
        yield loop_until(self.reactor,
                         self.is_container_deployment_complete,
                         repeat(2, 300))
        yield loop_until(self.reactor,
                         self.is_datasets_deployment_complete,
                         repeat(2, 300))

    def _build_config(self, ignored):
        """
        Build a Flocker deployment configuration for the given cluster
        and parameters.
        The configuration consists of identically configured applications
        (containers) uniformly spread over all cluster nodes.

        :param flocker.provision._common.Cluster cluster: The target cluster.
        :param dict application_template: A dictionary that provides configuration
                                      for an individual application.
        :param int per_node: The number of applications to deploy on each cluster
                             node.
        :return dict: The deployment configuration.
        """

        application_root = {}
        applications = {}
        application_root["version"] = 1
        application_root["applications"] = applications
        for node in self.nodes:
            for i in range(self.per_node):
                name = "app_%s_%d" % (node.public_address, i)
                applications[name] = deepcopy(self.application_template)

        deployment_root = {}
        nodes = {}
        deployment_root["nodes"] = nodes
        deployment_root["version"] = 1
        for node in self.nodes:
            addr = "%s" % node.public_address
            nodes[addr] = []
            for i in range(self.per_node):
                name = "app_%s_%d" % (node.public_address, i)
                nodes[addr].append(name)

        return {"applications": application_root,
                "deployment": deployment_root}

    def _configure(self, configuration):
        """
        Configure the cluster with the given deployment configuration.

        :param reactor: The reactor to use.
        :param flocker.provision._common.Cluster cluster: The target cluster.
        :param dict configuration: The deployment configuration.
        :return Deferred: Deferred that fires when the configuration is pushed
                          to the cluster's control agent.
        """
        base_url = b"https://{}:{}/v1".format(
            self.control_node_address, REST_API_PORT
        )
        cluster_cert = self.cluster_cert
        user_cert = self.user_cert
        user_key = self.user_key
        body = dumps(configuration)
        treq_client = treq_with_authentication(
            self.reactor, cluster_cert, user_cert, user_key)

        def do_configure():
            posted = treq_client.post(
                base_url + b"/configuration/_compose", data=body,
                headers={b"content-type": b"application/json"},
                persistent=False
            )

            def got_response(response):
                if response.code != OK:
                    d = json_content(response)

                    def got_error(error):
                        if isinstance(error, dict):
                            error = error[u"description"] + u"\n"
                        else:
                            error = u"Unknown error: " + unicode(error) + "\n"
                        raise ResponseError(response.code, error)

                    d.addCallback(got_error)
                    return d

            posted.addCallback(got_response)
            return posted

        return do_configure()



def main(reactor, argv):
    environ = os.environ
    options = ContainerOptions()
    options.parseOptions(argv[1:])
    container_deployment = ClusterContainerDeployment(reactor,
                                                      environ,
                                                      options)
    return container_deployment.deploy_and_wait_for_creation()
