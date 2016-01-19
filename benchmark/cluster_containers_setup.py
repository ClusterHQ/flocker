# Copyright ClusterHQ Inc.  See LICENSE file for details.
import yaml
import sys
from copy import deepcopy
from json import dumps
from itertools import repeat
from ipaddr import IPAddress

from treq import json_content
from eliot import add_destination, Message
from twisted.internet.defer import inlineCallbacks
from twisted.python.filepath import FilePath
from twisted.python import usage
from twisted.web.http import OK

from flocker.common import loop_until
from flocker.control.httpapi import REST_API_PORT
from flocker.apiclient import FlockerClient
from flocker.ca import treq_with_authentication


def eliot_output(message):
    """
    Write pretty versions of eliot log messages to stdout.
    """
    message_action = message.get('action')

    if message_action is not None:
        msg = "%s\n" % message_action
        sys.stdout.write(msg)
        sys.stdout.flush()


class ContainerOptions(usage.Options):
    """
    Parses the options passed as an argument to the create container script.
    """
    description = "Set up containers in a Flocker cluster."

    optParameters = [
        ['apps-per-node', None, 1, 'Number of application containers per node',
         int],
        ['app-template', None, None,
         'Configuration to use for each application container'],
        ['control-node', None, None,
         'Public IP address of the control node'],
        ['cert-directory', None, None,
         'Location of the user and control certificates and user key'],
        ['wait', None, None,
         "The timeout in seconds for waiting until the operation is complete. "
         "No waiting is done by default."],
    ]

    synopsis = ('Usage: setup-cluster-containers --app-per-node <containers '
                'per node> --app-template <name of the file> '
                '--control-node <IPAddress> '
                '--cert-directory <path where all the certificates are> '
                '[--wait <seconds to wait>]')

    def postOptions(self):
        # Mandatory parameters
        # Validate template
        if self['app-template'] is not None:
            template_file = FilePath(self['app-template'])
            self['template'] = yaml.safe_load(template_file.getContent())
        else:
            raise usage.UsageError(
                "app-template parameter must be provided"
            )
        # Validate app per node
        if self['apps-per-node'] is None:
            raise usage.UsageError("apps-per-node is a mandatory parameter")
        else:
            try:
                self['apps-per-node'] = int(self['apps-per-node'])
            except ValueError:
                raise usage.UsageError("apps-per-node has to be an integer")
        # Validate control node
        if self['control-node'] is None:
            raise usage.UsageError("control-node is a mandatory parameter")
        else:
            try:
                IPAddress(self['control-node'])
            except ValueError:
                raise usage.UsageError("control-node has to be an IP address")
        # Validate certificate directory
        if self['cert-directory'] is None:
            raise usage.UsageError("'cert-directory is a mandatory parameter")

        # Validate optional parameters
        if self['wait'] is not None:
            try:
                self['wait'] = int(self['wait'])
            except ValueError:
                raise usage.UsageError("The wait timeout must be an integer.")


def main(reactor, argv, environ):
    add_destination(eliot_output)

    try:
        options = ContainerOptions()
        options.parseOptions(argv[1:])
    except usage.UsageError as e:
        sys.stderr.write(e.args[0])
        sys.stderr.write('\n\n')
        sys.stderr.write(options.getSynopsis())
        sys.stderr.write('\n')
        sys.stderr.write(options.getUsage())
        raise SystemExit(1)
    container_deployment = ClusterContainerDeployment(reactor,
                                                      environ,
                                                      options)
    return container_deployment.deploy_and_wait_for_creation()


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

    :ivar options: ``ContainerOptions`` with the options passed to the script
    :ivar application_template: template of the containers to deploy.
    :ivar per_node: number of containers and dataset per node.
    :ivar control_node_address: public ip address of the control node.
    :ivar cluster_cert: ``FilePath`` of the cluster certificate.
    :ivar user_cert: ``FilePath`` of the user certificate.
    :ivar user_key: ``FilePath`` of the user key.
    :ivar client: ``FlockerClient`` conected to the cluster.
    :ivar reactor: ``Reactor`` used by the client.
    :ivar nodes: list of `Node` returned by client.list_nodes
    """
    def __init__(self, reactor, env, options):
        """
        ``ClusterContainerDeployment`` constructor.

        :param reactor: ``Reactor`` we are using.
        :param env: ``environ`` with the current environment.
            NOTE: alternative of making it work with env variables pending
            implementation
        :param options: ``ContainerOptions`` with the options passed to the
            the script.
        """
        self.options = options
        try:
            self.application_template = self.options['template']
            self.per_node = self.options['apps-per-node']
            self.control_node_address = self.options['control-node']
            self.timeout = self.options['wait']
            if self.timeout is None:
                # Wait two hours by default
                self.timeout = 72000
        except Exception as e:
            sys.stderr.write("%s: %s\n" % ("Missing or wrong arguments", e))
            sys.stderr.write(e.args[0])
            sys.stderr.write('\n\n')
            sys.stderr.write(options.getSynopsis())
            sys.stderr.write('\n')
            sys.stderr.write(options.getUsage())
            raise SystemExit(1)

        certificates_path = FilePath(self.options['cert-directory'])
        self.cluster_cert = certificates_path.child(b"cluster.crt")
        self.user_cert = certificates_path.child(b"user.crt")
        self.user_key = certificates_path.child(b"user.key")
        self.client = None
        self.reactor = reactor
        self.nodes = []
        self._initialise_client()

    def _initialise_client(self):
        """
        Initialise flocker client.
        """
        self.client = FlockerClient(
            self.reactor,
            self.control_node_address,
            REST_API_PORT,
            self.cluster_cert,
            self.user_cert,
            self.user_key
        )

    def _set_nodes(self, nodes):
        """
        Set the list of the nodes in the cluster.
        """
        self.nodes = nodes

    def deploy(self):
        """
        Deploy the new configuration: create the requested containers
        and dataset in the cluster nodes.

        :return Deferred: that will fire once the request to create all
            the containers and datasets has been sent.
        """
        Message.log(action="Listing current nodes")
        d = self.client.list_nodes()
        d.addCallback(self._set_nodes)
        d.addCallback(self._build_config)
        d.addCallback(self._configure)
        return d

    def is_datasets_deployment_complete(self):
        """
        Check if all the dataset have been created.

        :return Deferred: that will fire once the list datasets call
            has been completed, and which result will bee True if all the
            dataset have been created, or false otherwise.
        """
        number_of_datasets = self.per_node * len(self.nodes)

        d = self.client.list_datasets_state()

        def do_we_have_enough_datasets(datasets):
            msg = (
                "Waiting for the datasets to be ready..."
                "Created {current_datasets} of {total_datasets}"

            ).format(
                current_datasets=len(datasets),
                total_datasets=number_of_datasets,
            )
            Message.log(action=msg)

            return (len(datasets) >= number_of_datasets)

        d.addCallback(do_we_have_enough_datasets)
        return d

    def is_container_deployment_complete(self):
        """
        Check if all the containers have been created.

        :return Deferred: that will fire once the list containers call
            has been completed, and which result will bee True if all the
            containers have been created, or False otherwise.
        """
        number_of_containers = self.per_node * len(self.nodes)

        d = self.client.list_containers_state()

        def do_we_have_enough_containers(containers):
            msg = (
                "Waiting for the containers to be ready..."
                "Created {current_containers} of {total_containers}"

            ).format(
                current_containers=len(containers),
                total_containers=number_of_containers,
            )
            Message.log(action=msg)
            return (len(containers) >= number_of_containers)

        d.addCallback(do_we_have_enough_containers)
        return d

    @inlineCallbacks
    def deploy_and_wait_for_creation(self):
        """
        Function that will deploy the new configuration (create all the
        dataset and container requested) and will only return once all
        of them have been created.
        """
        yield self.deploy()
        yield loop_until(self.reactor,
                         self.is_datasets_deployment_complete,
                         repeat(1, self.timeout))
        yield loop_until(self.reactor,
                         self.is_container_deployment_complete,
                         repeat(1, self.timeout))

    def _build_config(self, ignored):
        """
        Build a Flocker deployment configuration for the given cluster
        and parameters.
        The configuration consists of identically configured applications
        (containers) uniformly spread over all cluster nodes.

        :return dict: containing the json we need to send to compose to
            create the datasets and containers we want.
        """
        Message.log(action="Building config")
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

        :param dict configuration: dictionary with the configuration
            to deploy.
        :return Deferred: Deferred that fires when the configuration is pushed
                          to the cluster's control agent.
        """
        Message.log(action="Deploying new config")
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
