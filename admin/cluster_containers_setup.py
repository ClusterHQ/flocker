
import string
import yaml
import os
from copy import deepcopy
import json

from jsonschema import ValidationError
from pyrsistent import pvector
from twisted.internet.defer import inlineCallbacks
from twisted.python.filepath import FilePath
from twisted.python import usage

from flocker.control.httpapi import REST_API_PORT
from flocker.apiclient import FlockerClient
from flocker.provision._common import Cluster
from benchmark.cluster import BenchmarkCluster, validate_host_mapping

from .cluster_setup import _configure

class ContainerOptions(usage.Options):
    description = "Set up containers in a Flocker cluster."

    optParameters = [
        ['apps-per-node', None, 0, 'Number of application containers per node',
         int],
        ['app-template', None, None,
         'Configuration to use for each application container'],
        ['purpose', None, 'testing',
         "Purpose of the cluster recorded in its metadata where possible"],
        ['cluster', None, None,
         'Configuration of the cluster'],

    ]

    synopsis = ('Usage: cluster-setup --distribution <distribution> '
                '[--provider <provider>]')

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


@inlineCallbacks
def main(reactor, argv):
    environ = os.environ
    print "\n\nGot env. Parsing options \n\n"
    options = ContainerOptions()
    options.parseOptions(argv[1:])
    client = get_flocker_client(reactor, environ)

    nodes = yield client.list_nodes()


    print "\n\n\n GOT CLUSTER"

    create_containers(reactor, nodes, options)

@inlineCallbacks
def create_containers(reactor, nodes, options):
    print "\n\n\n CREATING CONTAINERn"
    print options.items()

    print "\n\n\n"

    # TERRIBLE HACK!!! _build_config and _configure only need
    # the list of nodes. All the other fields of the cluster
    # are just garbagge here

    cluster = Cluster(
        all_nodes = pvector(nodes),
        control_node = nodes[0],
        agent_nodes = nodes,
        dataset_backend = "managed",
        default_volume_size = 1, #xxx
        certificate = None,
        dataset_backend_config_file = FilePath("/home/pilar/Documents/goals.txt"),
    )
    if options['apps-per-node'] > 0:
        config = _build_config(nodes, options['app-template'],
                               options['apps-per-node'])
        print "GOINT TO YIELD CONFIGURE!\n\n\n"
        yield _configure(reactor, cluster, config)


class ClusterContainerDeployment(object):
    def __init__(self, reactor, env, options):
        self.control_node_address = env['FLOCKER_ACCEPTANCE_CONTROL_NODE']
        self.certificates_path = FilePath(
            env['FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH'])
        try:
            self.host_to_public = json.loads(
                env['FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS']
            )
            validate_host_mapping(self.host_to_public)
        except ValueError as e:
            raise type(e)(
                ': '.join(
                    ('FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS',) + e.args
                )
            )

        self.cluster_cert = self.certificates_path.child(b"cluster.crt")
        self.user_cert = self.certificates_path.child(b"user.crt")
        self.user_key = self.selfcertificates_path.child(b"user.key")
        self.client = None
        self.options = options

    def initialise_client(self):
        self.client = self.FlockerClient(
            self.reactor,
            self.control_node_address,
            self.REST_API_PORT,
            self.cluster_cert,
            self.user_cert,
            self.user_key
        )

    def _build_config(self, nodes):
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
        application_template = self.options['app-template']
        per_node = self.options['apps-per-node']

        application_root = {}
        applications = {}
        application_root["version"] = 1
        application_root["applications"] = applications
        for node in nodes:
            for i in range(per_node):
                name = "app_%s_%d" % (node.private_address, i)
                applications[name] = deepcopy(application_template)

        deployment_root = {}
        nodes = {}
        deployment_root["nodes"] = nodes
        deployment_root["version"] = 1
        for node in nodes:
            nodes[node.private_address] = []
            for i in range(per_node):
                name = "app_%s_%d" % (node.private_address, i)
                nodes[node.private_address].append(name)

        return {"applications": application_root,
            "deployment": deployment_root}



def get_flocker_client(reactor, env):

    control_node_address = env['FLOCKER_ACCEPTANCE_CONTROL_NODE']
    certificates_path = FilePath(
    env['FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH'])
    try:
        host_to_public = json.loads(
            env['FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS']
        )
        validate_host_mapping(host_to_public)
    except ValueError as e:
        raise type(e)(
            ': '.join(
                ('FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS',) + e.args
            )
        )

    cluster_cert = certificates_path.child(b"cluster.crt")
    user_cert = certificates_path.child(b"user.crt")
    user_key = certificates_path.child(b"user.key")
    client = FlockerClient(reactor, control_node_address, REST_API_PORT,
                           cluster_cert, user_cert, user_key)
    return client

def get_cluster(options, env):
    """
    Obtain a cluster from the command line options and environment.

    :param BenchmarkOption options: Parsed command line options.
    :param dict env: Dictionary of environment variables.
    :return BenchmarkCluster: Cluster to benchmark.
    """
    print "\n\n GET CLUSTER OPTIONS: ", options
    print "\n\n CLUSTER ENVIRON", env
    cluster_option = options['cluster']
    if cluster_option:
        try:
            cluster = BenchmarkCluster.from_cluster_yaml(
                FilePath(cluster_option)
            )
        except IOError as e:
            usage(
                options, 'Cluster file {!r} not found.'.format(e.filename)
            )
    else:
        try:
            cluster = BenchmarkCluster.from_acceptance_test_env(env)
        except KeyError as e:
            usage(
                options, 'Environment variable {!r} not set.'.format(e.args[0])
            )
        except ValueError as e:
            usage(options, e.args[0])
        except ValidationError as e:
            usage(options, e.message)
    return cluster


def _configure(reactor, nodes, configuration):
    """
    Configure the cluster with the given deployment configuration.

    :param reactor: The reactor to use.
    :param flocker.provision._common.Cluster cluster: The target cluster.
    :param dict configuration: The deployment configuration.
    :return Deferred: Deferred that fires when the configuration is pushed
                      to the cluster's control agent.
    """
    base_url = b"https://{}:{}/v1".format(
        nodes[0].address, REST_API_PORT
    )
    certificates_path = cluster.certificates_path
    cluster_cert = certificates_path.child(b"cluster.crt")
    user_cert = certificates_path.child(b"user.crt")
    user_key = certificates_path.child(b"user.key")
    body = dumps(configuration)
    treq_client = treq_with_authentication(
        reactor, cluster_cert, user_cert, user_key)

    def got_all_nodes():
        d = treq_client.get(
            base_url + b"/state/nodes",
            persistent=False
        )
        d.addCallback(check_and_decode_json, OK)
        d.addCallback(
            lambda nodes: len(nodes) >= len(cluster.agent_nodes)
        )
        d.addErrback(write_failure, logger=None)
        return d

    got_nodes = loop_until(reactor, got_all_nodes, repeat(1, 300))

    def do_configure(_):
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

    configured = got_nodes.addCallback(do_configure)
    return configured
