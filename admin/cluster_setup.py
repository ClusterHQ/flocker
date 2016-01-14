# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Set up a Flocker cluster.
"""

import string
import sys
import yaml
from copy import deepcopy
from itertools import repeat
from json import dumps
from pipes import quote as shell_quote

from eliot import add_destination, write_failure, FileDestination

from treq import json_content

from twisted.internet.defer import inlineCallbacks
from twisted.python.filepath import FilePath
from twisted.python.usage import UsageError
from twisted.web.http import OK

from .acceptance import (
    ClusterIdentity,
    CommonOptions,
    capture_journal,
    capture_upstart,
    eliot_output,
    get_trial_environment,
)

from flocker.acceptance.testtools import check_and_decode_json
from flocker.ca import treq_with_authentication
from flocker.common import gather_deferreds, loop_until
from flocker.control.httpapi import REST_API_PORT


class RunOptions(CommonOptions):
    description = "Set up a Flocker cluster."

    optParameters = [
        ['apps-per-node', None, 0,
         "Number of application containers per node.", int],
        ['app-template', None, None,
         "Configuration to use for each application container."],
        ['purpose', None, 'testing',
         "Purpose of the cluster recorded in its metadata where possible."],
        ['cert-directory', None, None,
         "Directory for storing the cluster certificates. "
         "If not specified, then a temporary directory is used."],
    ]

    optFlags = [
        ["no-keep", None, "Do not keep VMs around (when testing)"],
    ]

    synopsis = ('Usage: cluster-setup --distribution <distribution> '
                '[--provider <provider>]')

    def __init__(self, top_level):
        """
        :param FilePath top_level: The top-level of the Flocker repository.
        """
        super(RunOptions, self).__init__(top_level)
        # Override default values defined in the base class.
        self['provider'] = self.defaults['provider'] = 'aws'
        self['dataset-backend'] = self.defaults['dataset-backend'] = 'aws'

    def postOptions(self):
        if self['app-template'] is not None:
            template_file = FilePath(self['app-template'])
            self['template'] = yaml.safe_load(template_file.getContent())
        elif self['apps-per-node'] > 0:
            raise UsageError(
                "app-template parameter must be provided if apps-per-node > 0"
            )

        self['purpose'] = unicode(self['purpose'])
        if any(x not in string.ascii_letters + string.digits + '-'
               for x in self['purpose']):
            raise UsageError(
                "Purpose may have only alphanumeric symbols and dash. " +
                "Found {!r}".format('purpose')
            )

        if self['cert-directory']:
            cert_path = FilePath(self['cert-directory'])
            _ensure_empty_directory(cert_path)
            self['cert-directory'] = cert_path

        # This is run last as it creates the actual "runner" object
        # based on the provided parameters.
        super(RunOptions, self).postOptions()

    def _make_cluster_identity(self, dataset_backend):
        purpose = self['purpose']
        return ClusterIdentity(
            purpose=purpose,
            prefix=purpose,
            name='{}-cluster'.format(purpose).encode("ascii"),
        )


def _ensure_empty_directory(path):
    """
    The path should not exist or it should be an empty directory.
    If the path does not exist then a new directory is created.

    :param FilePath path: The directory path to check or create.
    """
    if path.exists():
        if not path.isdir():
            raise UsageError("{} is not a directory".format(path.path))
        if path.listdir():
            raise UsageError("{} is not empty".format(path.path))
        return

    try:
        path.makedirs()
    except OSError as e:
        raise UsageError(
            "Can not create {}. {}: {}.".format(path.path, e.filename,
                                                e.strerror)
        )


@inlineCallbacks
def main(reactor, args, base_path, top_level):
    """
    :param reactor: Reactor to use.
    :param list args: The arguments passed to the script.
    :param FilePath base_path: The executable being run.
    :param FilePath top_level: The top-level of the Flocker repository.
    """
    options = RunOptions(top_level=top_level)

    add_destination(eliot_output)
    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    runner = options.runner

    from flocker.common.script import eliot_logging_service
    log_writer = eliot_logging_service(
        destination=FileDestination(
            file=open("%s.log" % (base_path.basename(),), "a")
        ),
        reactor=reactor,
        capture_stdout=False)
    log_writer.startService()
    reactor.addSystemEventTrigger(
        'before', 'shutdown', log_writer.stopService)

    cluster = None
    results = []
    try:
        yield runner.ensure_keys(reactor)
        cluster = yield runner.start_cluster(reactor)
        if options['distribution'] in ('centos-7',):
            remote_logs_file = open("remote_logs.log", "a")
            for node in cluster.all_nodes:
                results.append(capture_journal(reactor,
                                               node.address,
                                               remote_logs_file)
                               )
        elif options['distribution'] in ('ubuntu-14.04', 'ubuntu-15.10'):
            remote_logs_file = open("remote_logs.log", "a")
            for node in cluster.all_nodes:
                results.append(capture_upstart(reactor,
                                               node.address,
                                               remote_logs_file)
                               )
        gather_deferreds(results)

        if options['apps-per-node'] > 0:
            config = _build_config(cluster, options['template'],
                                   options['apps-per-node'])
            yield _configure(reactor, cluster, config)

        result = 0

    except BaseException:
        result = 1
        raise
    finally:
        if options['no-keep'] or result == 1:
            runner.stop_cluster(reactor)
        else:
            if cluster is None:
                print("Didn't finish creating the cluster.")
                runner.stop_cluster(reactor)
            else:
                print("The following variables describe the cluster:")
                environment_variables = get_trial_environment(cluster)
                for environment_variable in environment_variables:
                    print("export {name}={value};".format(
                        name=environment_variable,
                        value=shell_quote(
                            environment_variables[environment_variable]),
                    ))
                print("Be sure to preserve the required files.")

    raise SystemExit(result)


def _build_config(cluster, application_template, per_node):
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

    def node_address(node):
        if node.private_address is not None:
            return node.private_address
        else:
            return node.address

    for node in cluster.agent_nodes:
        for i in range(per_node):
            name = "app_%s_%d" % (node_address(node), i)
            applications[name] = deepcopy(application_template)

    deployment_root = {}
    nodes = {}
    deployment_root["nodes"] = nodes
    deployment_root["version"] = 1
    for node in cluster.agent_nodes:
        address = node_address(node)
        nodes[address] = list()
        for i in range(per_node):
            name = "app_%s_%d" % (address, i)
            nodes[address].append(name)

    return {"applications": application_root,
            "deployment": deployment_root}


class ResponseError(Exception):
    """
    An unexpected response from the REST API.
    """
    def __init__(self, code, message):
        Exception.__init__(self, "Unexpected response code {}:\n{}\n".format(
            code, message))
        self.code = code


def _configure(reactor, cluster, configuration):
    """
    Configure the cluster with the given deployment configuration.

    :param reactor: The reactor to use.
    :param flocker.provision._common.Cluster cluster: The target cluster.
    :param dict configuration: The deployment configuration.
    :return Deferred: Deferred that fires when the configuration is pushed
                      to the cluster's control agent.
    """
    base_url = b"https://{}:{}/v1".format(
        cluster.control_node.address, REST_API_PORT
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
